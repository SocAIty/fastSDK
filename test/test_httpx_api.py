import httpx
import asyncio
from urllib.parse import urljoin

async def test_fastapi_embeddings():
    base_url = "http://localhost:8000"
    url = f"{base_url}/embeddings"
    
    data = {
        "model": "Qwen",
        "input": "Hello world"
    }
    
    async with httpx.AsyncClient() as client:
        # Initial request to queue the job
        response = await client.post(
            url,
            json=data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Initial Status: {response.status_code}")
        result = response.json()
        print(f"Initial Response: {result}")
        
        # Get the refresh URL and make it absolute
        refresh_url = result.get("refresh_job_url")
        if not refresh_url:
            print("No refresh_job_url found, job might be completed immediately")
            return result
        
        # Convert relative URL to absolute URL
        if not refresh_url.startswith(("http://", "https://")):
            refresh_url = urljoin(base_url, refresh_url)
        
        # Poll the refresh URL until job is completed
        print(f"\nPolling job status at: {refresh_url}")
        max_attempts = 60  # Maximum polling attempts
        poll_interval = 1  # Seconds between polls
        
        for attempt in range(max_attempts):
            await asyncio.sleep(poll_interval)
            
            # Use POST instead of GET
            status_response = await client.post(refresh_url)
            status_data = status_response.json()
            
            job_status = status_data.get("status")
            print(f"Attempt {attempt + 1}: Status = {job_status}")
            
            # Check if job is completed
            if job_status in ["Finished", "completed", "success", "done", "Completed", "Success"]:
                print(f"\n✅ Job completed!")
                print(f"Final Response: {status_data}")
                return status_data
            
            # Check if job failed
            elif job_status in ["failed", "error", "Failed", "Error"]:
                print(f"\n❌ Job failed!")
                print(f"Error Response: {status_data}")
                raise Exception(f"Job failed: {status_data}")
            
            # Continue polling for pending/processing status
            elif job_status in ["pending", "processing", "queued", "Queued", "Pending", "Processing"]:
                # Show progress if available
                progress = status_data.get("progress", {})
                if progress:
                    progress_pct = progress.get("progress", 0)
                    progress_msg = progress.get("message", "")
                    print(f"  Progress: {progress_pct}% - {progress_msg}")
                continue
            
            else:
                print(f"⚠️  Unknown status: {job_status}")
        
        # If we exit the loop, we've exceeded max attempts
        raise TimeoutError(f"Job did not complete after {max_attempts} attempts")


# Synchronous version
def test_fastapi_embeddings_sync():
    import time
    from urllib.parse import urljoin
    
    base_url = "http://localhost:8000"
    url = f"{base_url}/embeddings"
    
    data = {
        "model": "Qwen",
        "input": "Hello world"
    }
    
    with httpx.Client() as client:
        # Initial request
        response = client.post(url, json=data)
        
        print(f"Initial Status: {response.status_code}")
        result = response.json()
        print(f"Initial Response: {result}")
        
        # Get the refresh URL and make it absolute
        refresh_url = result.get("refresh_job_url")
        if not refresh_url:
            print("No refresh_job_url found, job might be completed immediately")
            return result
        
        # Convert relative URL to absolute URL
        if not refresh_url.startswith(("http://", "https://")):
            refresh_url = urljoin(base_url, refresh_url)
        
        # Poll the refresh URL
        print(f"\nPolling job status at: {refresh_url}")
        max_attempts = 60
        poll_interval = 1
        
        for attempt in range(max_attempts):
            time.sleep(poll_interval)
            
            # Use POST instead of GET
            status_response = client.post(refresh_url)
            status_data = status_response.json()
            
            job_status = status_data.get("status")
            print(f"Attempt {attempt + 1}: Status = {job_status}")
            
            if job_status in ["completed", "success", "done", "Completed", "Success"]:
                print(f"\n✅ Job completed!")
                print(f"Final Response: {status_data}")
                return status_data
            
            elif job_status in ["failed", "error", "Failed", "Error"]:
                print(f"\n❌ Job failed!")
                print(f"Error Response: {status_data}")
                raise Exception(f"Job failed: {status_data}")
            
            elif job_status in ["pending", "processing", "queued", "Queued", "Pending", "Processing"]:
                progress = status_data.get("progress", {})
                if progress:
                    progress_pct = progress.get("progress", 0)
                    progress_msg = progress.get("message", "")
                    print(f"  Progress: {progress_pct}% - {progress_msg}")
                continue
            
            else:
                print(f"⚠️  Unknown status: {job_status}")
        
        raise TimeoutError(f"Job did not complete after {max_attempts} attempts")


if __name__ == "__main__":
    asyncio.run(test_fastapi_embeddings())