<h1>Overview</h1>
<p>Elastic Face Recognition is a three-tier Python application that performs deep-learning face classification while autoscaling its compute tier on Amazon EC2. A single web-tier instance receives images, queues lightweight jobs, and returns predictions; up to 15 application-tier instances spin up on demand, handle inference, then shut down to zero cost when idle. All resources reside in us-east-1 and respect the naming/size constraints required by the course autograder. ​
</p>

<h1>Architecture</h1>
<p>
<ul>
<li>Compute: AWS EC2 (t2.micro), custom AMI</li>
<li>Storage: Amazon S3 (input/output buckets)</li>
<li>Messaging: Amazon SQS (request/response queues)</li>
<li>ML Framework: PyTorch 2.x (CPU), facenet-pytorch</li>
<li>Runtime: Python 3.12, Flask, boto3</li>
</ul>
</p>
