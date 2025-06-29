from fastapi import APIRouter, Request, Response, HTTPException, Security
from fastapi.responses import StreamingResponse
from typing import Optional
import os
import xml.etree.ElementTree as ET

from security import get_api_key
from storage import get_bucket_path, get_object_path, settings

router = APIRouter(prefix="/s3", tags=["s3 - DRAFT"])

def build_xml_list_bucket(bucket_name: str, files: list):
    root_elem = ET.Element("ListBucketResult", xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
    ET.SubElement(root_elem, "Name").text = bucket_name
    ET.SubElement(root_elem, "KeyCount").text = str(len(files))
    contents_elem = []
    for key in files:
        content = ET.SubElement(root_elem, "Contents")
        ET.SubElement(content, "Key").text = key
        ET.SubElement(content, "Size").text = str(os.path.getsize(os.path.join(get_bucket_path(bucket_name), key)))
    return ET.tostring(root_elem, encoding="utf-8", xml_declaration=True)

@router.put("/{bucket_name}/{object_key:path}")
async def s3_put_object(bucket_name: str, object_key: str, request: Request, api_key: str = Security(get_api_key)):
    content = await request.body()
    bucket_path = get_bucket_path(bucket_name)
    os.makedirs(bucket_path, exist_ok=True)
    file_path = get_object_path(bucket_name, object_key)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(content)
    return Response(status_code=200)

@router.get("/{bucket_name}/{object_key:path}")
async def s3_get_object(bucket_name: str, object_key: str, api_key: str = Security(get_api_key)):
    file_path = get_object_path(bucket_name, object_key)
    if not os.path.isfile(file_path):
        raise HTTPException(404)
    def iterfile():
        with open(file_path, "rb") as f:
            yield from f
    return StreamingResponse(iterfile(), media_type="application/octet-stream")

@router.delete("/{bucket_name}/{object_key:path}")
async def s3_delete_object(bucket_name: str, object_key: str, api_key: str = Security(get_api_key)):
    file_path = get_object_path(bucket_name, object_key)
    if os.path.isfile(file_path):
        os.remove(file_path)
        return Response(status_code=204)
    raise HTTPException(404)

@router.get("/{bucket_name}")
async def s3_list_objects(bucket_name: str, prefix: Optional[str] = None, api_key: str = Security(get_api_key)):
    bucket_path = get_bucket_path(bucket_name)
    if not os.path.isdir(bucket_path):
        raise HTTPException(404)
    files_list = []
    for root, dirs, files in os.walk(bucket_path):
        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), bucket_path)
            if prefix and not rel_path.startswith(prefix):
                continue
            files_list.append(rel_path)
    xml_resp = build_xml_list_bucket(bucket_name, files_list)
    return Response(content=xml_resp, media_type="application/xml")
