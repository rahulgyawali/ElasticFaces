import boto3
import logging
import time
import uuid
import threading
from flask import Flask, request

REGION = "us-east-1"
S3_BUCKET_NAME = "1229604729-in-bucket"
REQ_Q_NAME = "https://sqs.us-east-1.amazonaws.com/038462753394/1229604729-req-queue"
RESP_Q_NAME = "https://sqs.us-east-1.amazonaws.com/038462753394/1229604729-resp-queue"
PORT = 8000
TIME_OUT = 50  

LOG_REQUEST = "Request received for input"
ERROR_S3 = "Error Uploading to S3"
SUCCESS_S3 = "Uploaded Successfully to S3 for"
ERROR_PUSH_SQS = "Error pushing to Queue"
SUCCESS_PUSH_SQS = "Message pushed to request queue for "
SUCCESS_PULL_SQS = "Message pulled from response queue"
ERROR_PULL_SQS = "Error pulling from queue"

s3 = boto3.client("s3", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)

results_map = {}

def response_queue_poller():
    while True:
        try:
            resp = sqs.receive_message(QueueUrl=RESP_Q_NAME,MaxNumberOfMessages=10,WaitTimeSeconds=5)
            messages = resp.get("Messages", [])
            for msg in messages:
                body = msg["Body"]
                logging.info(f"Received response message: {body}")
                parts = body.split(":")
                if len(parts) < 3:
                    logging.warning(f"Invalid response message format: {body}")
                    sqs.delete_message(QueueUrl=RESP_Q_NAME, ReceiptHandle=msg["ReceiptHandle"])
                    continue
                request_id = parts[0]
                filename = parts[1]
                recognized_name = parts[2]
                # store in cache
                results_map[(request_id, filename)] = recognized_name
                # delete message from response  queue
                sqs.delete_message(QueueUrl=RESP_Q_NAME, ReceiptHandle=msg["ReceiptHandle"])
                logging.info(f"{SUCCESS_PULL_SQS}: Saved prediction for {request_id}:{filename}")
        except Exception as e:
            logging.error(f"{ERROR_PULL_SQS}: {str(e)}")
        time.sleep(0.5)

#push objec to input s3
def upload_to_s3(file_obj, key_name):
    try:
        s3.upload_fileobj(file_obj, S3_BUCKET_NAME, key_name)
        logging.info(f"{SUCCESS_S3} {key_name}")
    except Exception as e:
        logging.error(f"{ERROR_S3}: {str(e)}")

#push request to request queue
def push_to_sqs(request_id, filename):
    try:
        body = f"{request_id}:{filename}"
        sqs.send_message(QueueUrl=REQ_Q_NAME, MessageBody=body)
        logging.info(f"{SUCCESS_PUSH_SQS}{body}")
    except Exception as e:
        logging.error(f"{ERROR_PUSH_SQS}: {str(e)}")

app = Flask(__name__)

@app.route("/", methods=["POST"])
def handle_request():
    if "inputFile" not in request.files:
        return "Bad Request: 'inputFile' missing", 200
    
    file_obj = request.files["inputFile"]
    filename_with_extension = file_obj.filename
    if not filename_with_extension:
        return "Bad Request: No filename provided", 200

    logging.info(f"{LOG_REQUEST} {filename_with_extension}")
    request_id = str(uuid.uuid4())
    upload_to_s3(file_obj, filename_with_extension)
    push_to_sqs(request_id, filename_with_extension)
    start_time = time.time()
    while time.time() - start_time < TIME_OUT:
        if (request_id, filename_with_extension) in results_map:
            recognized_name = results_map[(request_id, filename_with_extension)]
            filename_only = filename_with_extension.rsplit(".", 1)[0]
            return f"{filename_only}:{recognized_name}", 200
        time.sleep(0.5)

    return "Unknown", 200

if __name__ == "__main__":
    thread = threading.Thread(target=response_queue_poller, daemon=True)
    thread.start()   
    app.run(host="0.0.0.0", port=PORT, threaded=True)
