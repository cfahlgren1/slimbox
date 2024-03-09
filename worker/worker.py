from rq import Worker
from dotenv import load_dotenv
from redis import Redis
import os

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
service_role_key = os.getenv("SUPABASE_KEY")
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = os.getenv("REDIS_PORT", 6379)

if __name__ == "__main__":
    print("Starting worker")
    w = Worker(["default"], connection=Redis(host=redis_host, port=redis_port))
    w.work()
