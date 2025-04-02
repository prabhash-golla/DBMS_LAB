import aiohttp
import asyncio
import random
import time


class Read(asyncio.Future):
    @staticmethod
    def is_compatible(holds):
        return not holds[Write]


class Write(asyncio.Future):
    @staticmethod
    def is_compatible(holds):
        return not holds[Read] and not holds[Write]


def random_hostname():
    return f'Server-{random.randrange(0, 1000):03}-{int(time.time()*1e3) % 1000:03}'


def err_payload(err: Exception):
    return {
        'message': f'<Error> {err}',
        'status': 'failure'
    }


async def gather_with_concurrency(
    session: aiohttp.ClientSession,
    batch: int,
    *urls: str
):

    await asyncio.sleep(0)

    semaphore = asyncio.Semaphore(batch)

    async def fetch(url: str):
    
        await asyncio.sleep(0)

        async with semaphore:
            async with session.get(url) as response:
                await response.read()

            return response
    


    tasks = [fetch(url) for url in urls]

    return [None if isinstance(r, BaseException)
            else r for r in
            await asyncio.gather(*tasks, return_exceptions=True)]