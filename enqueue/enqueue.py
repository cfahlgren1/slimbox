from supabase import create_client, Client
from enqueue.tasks import read_and_label_emails
from dotenv import load_dotenv
from datetime import datetime, timedelta
from redis import Redis
from rq import Queue
from rich.console import Console
from rich.table import Table
import asyncio
import os

load_dotenv("../")
console = Console()

supabase_url = os.getenv("SUPABASE_URL")
service_role_key = os.getenv("SUPABASE_KEY")

redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))

supabase: Client = create_client(supabase_url, service_role_key)

redis_conn = Redis(host=redis_host, port=redis_port)
q = Queue(connection=redis_conn)

console.print(
    f"Redis host: [yellow]{redis_host}[/yellow], Redis port: [yellow]{redis_port}[/yellow]",
    style="bold green",
)


async def fetch_and_enqueue_users():
    console.print("Fetching and enqueuing users", style="bold magenta")
    active_users_response = (
        supabase.table("user_cron_schedules")
        .select("user_id,last_run_at")
        .eq("paused", False)
        .execute()
    )
    active_users = active_users_response.data
    if active_users and len(active_users) > 0:
        table = Table(title="Active Users")
        table.add_column("User ID", style="cyan", no_wrap=True)
        table.add_column("Last Run At", style="cyan", no_wrap=True)
        table.add_column("Enqueued", style="green")

        for row in active_users:
            user_id = row["user_id"]
            last_run_at = row["last_run_at"] or "Never"
            task = q.enqueue(read_and_label_emails, user_id)
            enqueued_status = "Yes" if task else "No"
            table.add_row(str(user_id), str(last_run_at), enqueued_status)

        console.print(table)
    else:
        console.print("No active users to enqueue", style="yellow")

    console.print("Done fetching and enqueuing users", style="bold magenta")


async def run_every_interval(interval):
    while True:
        await fetch_and_enqueue_users()
        await asyncio.sleep(interval)


if __name__ == "__main__":
    interval_seconds = 30  # Run every 30 seconds
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_every_interval(interval_seconds))
