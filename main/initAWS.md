## Initial Setup for EC2 Instance (Ubuntu 22.04)
```sh
sudo apt update
sudo apt install -y python3 python3-pip git unzip zip python3-venv git-lfs
snap install aws-cli --classic
python3 -m venv acct-cik
source acct-cik/bin/activate
pip install pandas requests beautifulsoup4 tqdm psutil
```
### Grab a file from a S3 Bucket
```sh
# Download a file from s3
aws s3 cp s3://my-bucket/my-file ./
# Upload a file to s3
aws s3 cp ./my-file s3://my-bucket/my-file
```
### Run a Python Script in the Background
```sh
screen -S session
python3 script.py
# Press Ctrl+A then D to detach
screen -r session  # To reattach
```
### Create an ssh-key
```sh
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
# cat ~/.ssh/id_rsa.pub and move it to authorized_keys file on the server you want to access
```
