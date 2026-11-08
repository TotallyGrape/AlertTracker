"""One live fetch per enabled adapter; saves compact results, never starts polling."""
import asyncio
import json
import httpx
from app.main import ENABLED, collect


async def main():
    async with httpx.AsyncClient(timeout=60, headers={'User-Agent': 'TexasResponse-Hackathon/0.1'}) as client:
        async def check(source):
            try:
                result = await collect(source, client)
                return source, {'ok': True, 'pins': sum(p['latitude'] is not None for p in result['items']),
                                'unlocated': sum(p['latitude'] is None for p in result['items']),
                                'boundaries': len(result['boundaries'])}
            except Exception as exc:
                return source, {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
        results = dict(await asyncio.gather(*(check(s) for s in ENABLED)))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
