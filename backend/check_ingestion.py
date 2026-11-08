"""Check the deployed ingestion route rejects unauthorized and malformed requests."""
import asyncio
import os
from app import main as m
import httpx


async def check():
    url, secret = os.environ['SPACETIME_INGEST_URL'], os.environ['SPACETIME_INGEST_SECRET']
    async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=3, max_keepalive_connections=0)) as client:
        response = await client.post(url, json={})
        assert response.status_code == 401, response.status_code
        response = await client.post(url, headers={'x-ingest-secret': secret}, json={})
        assert response.status_code == 400, response.status_code
        print('Authentication and payload rejection passed')


if __name__ == '__main__':
    asyncio.run(check())
