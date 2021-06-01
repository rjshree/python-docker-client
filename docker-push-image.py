import docker
import flask, requests, json
from flask import request, jsonify,  Response
import os, tarfile
from io import BytesIO
from docker import models
import logging
from requests.auth import HTTPBasicAuth
import time

# The flask app for serving predictions
app = flask.Flask(__name__)
logger = logging.getLogger()

logging.basicConfig(level=logging.INFO)
logger.setLevel(os.getenv("LOG_LEVEL",logging.INFO))


client = docker.from_env()



def docker_push(image_name, nexus_password):
    logger.info("Docker push started")
    tag = os.getenv("NEXUS_URL","10.177.197.204:40123")+"/docker-eai/"+image_name.split("/")[-1]
    tag_response = client.images.get(image_name).tag(tag)
    logger.info(f"tag response {tag}, {tag_response}, {nexus_password}")
    # push_response = client.images.push(tag, auth_config={"username": "admin","password": nexus_password,"registry": os.getenv("NEXUS_URL","cp-nexus-0.novalocal:5556")})
    # logger.info(push_response)
    sha256 = ""
    for line in client.images.push(tag, stream=True, decode=True):
        logger.info(line)
        # out = json.loads(line)
        # if "aux" in out:
        #     logger.info("*******sha256***", out["aux"]["Digest"].split(":")[-1])
        #     sha256 = out["aux"]["Digest"].split(":")[-1]
    # out = push_response.split('\r\n')[-2]
    # out = json.loads(out)
    # logger.info("*******sha256***",out["aux"]["Digest"].split(":")[-1])
    # return {"image":tag,"sha256":out["aux"]["Digest"].split(":")[-1]}
    return tag


def docker_nexus_login():
    nexus_password = {}
    # nexus_password = requests.get(os.getenv("NEXUS_SECRET_URL","http://cp-sw-install-0.novalocal:6000/eis/v1/system/secret/nexus_password"), timeout=60)
    # logger.info(f"nexus password is {nexus_password.text}")
    # nexus_password = json.loads(nexus_password.text)
    # response = client.login('admin', password=nexus_password['nexus_password'], registry=os.getenv("NEXUS_URL","cp-nexus-0.novalocal:5556"))
    response = client.login('admin', password='sZGgsZba', registry=os.getenv("NEXUS_URL","10.177.197.204:40123"))
    logger.info(f"Docker login successful {response}")
    return nexus_password if nexus_password.get('nexus_password') else os.getenv("NEXUS_PASSWORD", "sZGgsZba")

@app.route('/upload', methods=['POST'])
def invocations():
    start = time.time()
    push_response = {}

    response = "Started {} {}"
    try:
        nexus_password = docker_nexus_login()
        logger.info("request.content_type: {}".format(request.content_type))
        # if request.content_type in ['application/x-tar', "text/plain"]:
            # Read data from request
        try:
            tar_file = request.data
            load_response = client.images.load(tar_file)
            logger.info(f"Response of loaded image {load_response[0].attrs['RepoDigests']}")
            if isinstance(load_response[0], models.images.Image):
                image_name = str(load_response[0].tags.pop())
                logger.info(f'extracted image name {image_name} {type(image_name)}')
            push_response = {"image":docker_push(image_name, nexus_password)}
            result_image = client.images.get(push_response["image"])
            sha256=result_image.attrs["RepoDigests"][0].split(":")[-1]
            logger.info(f'Docker push response {sha256}{result_image}{response}')
            push_response["sha256"] = sha256
        except Exception as e:
            raise Exception(e)

        # else:
        #     response = "Content error {} {}"
        #     response = response.format("ERROR", "Invalid request content type.")
    except Exception as exc:
        response = "Exception {} {}"
        response = response.format("ERROR", exc)
        logger.info(response)
    end = time.time()
    logger.info(end - start)
    return jsonify(push_response)

@app.route('/asset/<sha256_code>', methods=['DELETE'])
def delete_asset(sha256_code="90659bf80b44ce6be8234e6ff90a1ac34acbeb826903b02cfa0da11c82cbc042"):
    assetId_list = []
    asset_response_list = []
    asset_items = requests.get(os.getenv("NEXUS_ASSET_URL","http://10.177.197.201:8081/service/rest/v1/assets?repository=docker-eai"),
                auth = HTTPBasicAuth('admin', 'sZGgsZba'))
    asset_items = asset_items.json()
    for asset in asset_items["items"]:
        # if sha256_code in asset["checksum"]["sha256"]:
        assetId_list.append(asset["id"])

    for assetId in assetId_list:
        NEXUS_ASSET_DELETE_URL = os.getenv("NEXUS_ASSET_DELETE_URL","http://10.177.197.201:8081") + "/service/rest/v1/assets/" +assetId
        logger.info(f"NEXUS_ASSET_DELETE_URL {NEXUS_ASSET_DELETE_URL}")
        asset_response = requests.request("DELETE", NEXUS_ASSET_DELETE_URL, auth=HTTPBasicAuth('admin', 'sZGgsZba'))
        asset_response_list.append(asset_response)
    return jsonify({"sha256": sha256_code, "deleted": True})

@app.route('/quota-status', methods=['GET'])
def get_blob_store_quota():
    quota_status_url = f"http://10.177.197.201:8081/service/rest/v1/blobstores/incluster-minio/quota-status"
    blob_store_response = requests.get(os.getenv("NEXUS_BLOB_STORE_QUOTA_URL", quota_status_url),
                               auth=HTTPBasicAuth('admin', 'sZGgsZba'))
    logger.info(f"blob store quota {blob_store_response}")
    return Response(
    response=blob_store_response.text,
    status=blob_store_response.status_code,
    headers=dict(blob_store_response.headers)
    )

@app.route('/blobstore', methods=['POST'])
def create_blobstore():
    payload = request.data
    print(payload)
    response = requests.post(os.getenv("NEXUS_URL","http://10.177.197.201:8081/service/rest/v1/blobstores/file"), data=payload, headers={'Accept': 'application/json','Content-Type': 'application/json'})
    print(response)
    return jsonify(response.text)


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
