import boto3
import time
import logging

REGION_NAME = "us-east-1"
REQ_Q_URL = "https://sqs.us-east-1.amazonaws.com/038462753394/1229604729-req-queue"
RESP_Q_URL = "https://sqs.us-east-1.amazonaws.com/038462753394/1229604729-resp-queue"
MAX_APP_INSTANCES = 15
POLL_INTERVAL = 5   
APP_TIER_NAME_TAG = "app-tier-instance"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

sqs = boto3.client("sqs", region_name=REGION_NAME)
ec2 = boto3.resource("ec2", region_name=REGION_NAME)

time_of_surpluse_instance = None

#find total messages in queue
def total_messages_in_queue(url):
    attrs = sqs.get_queue_attributes(
        QueueUrl=url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
    )
    total_message = int(attrs["Attributes"].get("ApproximateNumberOfMessages", 0))
    return total_message

#find total instances
def total_instances():
    filters = [
        {"Name": "tag:Name", "Values": [APP_TIER_NAME_TAG + "-*"]},
        {"Name": "instance-state-name", "Values": ["pending", "running","stopped"]}
    ]
    instance_list = list(ec2.instances.filter(Filters=filters))
    return instance_list

#Perform scale out from stopped instances
def scale_out(required_instance, current_stopped_instance):
    if required_instance > 0 and current_stopped_instance:
        instance_ids = [inst.id for inst in current_stopped_instance[:required_instance]]
        logging.info(f"Adding instances with id{instance_ids}")
        try:
            ec2.start_instances(InstanceIds=instance_ids)
        except Exception as e:
            logging.error(f"Error while adding {instance_ids}: {e}")

#scale in using active instance
def scale_in(required_instance, current_active_instance):
    instances_to_stop = current_active_instance[required_instance:]
    instance_ids = [inst.id for inst in instances_to_stop]
    if instance_ids:
        logging.info(f"Removing instances with ids: {instance_ids}")
        try:
            ec2.stop_instances(InstanceIds=instance_ids)
        except Exception as e:
            logging.error(f"Error stopping instances {instance_ids}: {e}")


#actual auto scale method
def custom_auto_scale():
    global time_of_surpluse_instance
    while True:
        #Find total message in request queue
        total_req_msgs = total_messages_in_queue(REQ_Q_URL)
        #Find total instance running
        total_available_instance = total_instances()
        total_active_instance = [inst for inst in total_available_instance if inst.state["Name"] in ["running", "pending"]]
        total_stopped_instance = [inst for inst in total_available_instance if inst.state["Name"] == "stopped"]
        logging.info(f"Queue={total_req_msgs}, Total Active={len(total_active_instance)}, Total Stopped={len(total_stopped_instance)}")

        desired_count = min(total_req_msgs, MAX_APP_INSTANCES)
        logging.debug(f"Required instance instance count: {desired_count}")
        #Sclae out if required count is greater than active
        if desired_count > len(total_active_instance):
            instances_needed = desired_count - len(total_active_instance)
            time_of_surpluse_instance = None  
            scale_out(instances_needed, total_stopped_instance)
        #Scale in if required count is lesser than active
        elif desired_count < len(total_active_instance) :
            time_of_surpluse_instance = time.time()
            #Check if the instances are in surplus for more than poll interval
            if time.time() - time_of_surpluse_instance >= POLL_INTERVAL:
                scale_in(total_active_instance, desired_count)
        #Reset the timer for surplus
        else:
            time_of_surpluse_instance = None
        time.sleep(2)

if __name__ == "__main__":
    custom_auto_scale()
