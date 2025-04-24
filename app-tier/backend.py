import boto3
import os
import time
import logging
from io import BytesIO
from PIL import Image
import requests
import torch
from facenet_pytorch import MTCNN, InceptionResnetV1

REGION = "us-east-1"
S3_INPUT_BUCKET_NAME = "1229604729-in-bucket"
S3_OUTPUT_BUCKET_NAME = "1229604729-out-bucket"
REQ_Q_NAME = "https://sqs.us-east-1.amazonaws.com/038462753394/1229604729-req-queue"
RESP_Q_NAME = "https://sqs.us-east-1.amazonaws.com/038462753394/1229604729-resp-queue"
PATH_OF_WEIGHTS = "data.pt"

mtcnn_detector = MTCNN(image_size=240, margin=0, min_face_size=20)
face_recognizer = InceptionResnetV1(pretrained='vggface2').eval()
s3 = boto3.client("s3", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)

saved_data = torch.load(PATH_OF_WEIGHTS)
embedding_list = saved_data[0]
name_list = saved_data[1]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def face_match(image_bytes):
    image = Image.open(BytesIO(image_bytes))
    with torch.no_grad():
        face_tensor, prob = mtcnn_detector(image, return_prob=True)
        embedding = face_recognizer(face_tensor.unsqueeze(0))
    distances = [torch.dist(embedding, emb_db).item() for emb_db in embedding_list]
    min_index = distances.index(min(distances))
    recognized_name = name_list[min_index]
    min_distance = min(distances)
    return recognized_name, min_distance

def main():
    while True:
        response = sqs.receive_message(
            QueueUrl=REQ_Q_NAME,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5
        )
        messages = response.get("Messages", [])
        if not messages:
            continue

        for msg in messages:
            body = msg["Body"]
            parts = body.split(":")
            if len(parts) < 2:
                logger.error(f"Invalid message format: {body}, deleting message")
                sqs.delete_message(QueueUrl=REQ_Q_NAME, ReceiptHandle=msg["ReceiptHandle"])
                continue

            request_id, image_name = parts[0], parts[1]
            logger.info(f"Received message: request_id={request_id}, filename={image_name}")

            try:
                #Download image from Input Bucket
                s3_response = s3.get_object(Bucket=S3_INPUT_BUCKET_NAME, Key=image_name)
                logger.info(f"Downloaded {image_name} from S3 bucket {S3_INPUT_BUCKET_NAME}")

                image_data = s3_response["Body"].read()

                #Invoke Face Match method for image data
                recognized_name, distance_val = face_match(image_data)
                logger.info(f"Result: Name: {recognized_name}, similarity distance={distance_val}")
                image_name_only = image_name.rsplit(".", 1)[0]
                output_path_s3 = f"/tmp/{image_name_only}.txt"
                with open(output_path_s3,"w") as f:
                     f.write(recognized_name)

                #upload result to output bucket
                s3.upload_file(output_path_s3,S3_OUTPUT_BUCKET_NAME,f"{image_name_only}.txt")
                response_body = f"{request_id}:{image_name}:{recognized_name}"

                #send message in response queue
                sqs.send_message(QueueUrl=RESP_Q_NAME, MessageBody=response_body)
                logger.info(f"Sent response message: {response_body}")
                
                #delete message from request quque 
                sqs.delete_message(QueueUrl=REQ_Q_NAME, ReceiptHandle=msg["ReceiptHandle"])
                logger.info("Deleted request message from queue.")

            except Exception as e:
                logger.error(f"Error processing {image_name}: {str(e)}")
                sqs.delete_message(QueueUrl=REQ_Q_NAME, ReceiptHandle=msg["ReceiptHandle"])
                logger.info("Deleted message due to error.")

        time.sleep(0.5)

if __name__ == "__main__":
    main()
