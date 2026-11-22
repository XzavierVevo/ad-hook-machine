import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from . import config

class RateLimiter:
    """
    Simple rate limiter to manage API call frequency.
    """
    def __init__(self, rpm_limit: int):
        self.rpm_limit = rpm_limit
        self.interval = 60.0 / rpm_limit if rpm_limit > 0 else 0
        self.last_call_time = 0
        self.lock = threading.Lock()

    def wait(self):
        """Wait if necessary to stay within the rate limit."""
        if self.rpm_limit <= 0:
            return

        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_call_time
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
            self.last_call_time = time.time()


class MetaRateLimiter:
    """
    Rate limiter for Meta Marketing API to stay within development tier limits.
    Now monitors X-Business-Use-Case-Usage and X-Ad-Account-Usage headers.
    """
    def __init__(self, max_score: int = 60, window_seconds: int = 300):
        self.max_score = max_score
        self.window_seconds = window_seconds
        self.calls = []  # List of (timestamp, points)
        self.lock = threading.Lock()
        self.blocked_until = 0

    def wait(self, points: int = 1, context: str = "API Call"):
        """
        Wait if necessary based on local score or remote block.
        
        Args:
            points: Score assigned to the call (1 for read, 3 for write, or N for ads)
            context: Description of the call for logging
        """
        while True:
            wait_time = 0
            current_score = 0
            block_reason = ""
            now = time.time()
            
            with self.lock:
                # Check if we are explicitly blocked by a header response
                if now < self.blocked_until:
                    wait_time = self.blocked_until - now
                    block_reason = "Remote Header Block"
                else:
                    # Fallback to score tracking
                    self.calls = [c for c in self.calls if now - c[0] < self.window_seconds]
                    current_score = sum(c[1] for c in self.calls)
                    
                    if current_score + points <= self.max_score:
                        self.calls.append((now, points))
                        return
                    
                    if self.calls:
                        wait_time = self.calls[0][0] + self.window_seconds - now
                        block_reason = f"Local Score Limit ({current_score}/{self.max_score})"
            
            if wait_time > 0:
                print(f"[RATE LIMIT] {context} paused for {wait_time:.1f}s. Reason: {block_reason}")
                time.sleep(wait_time + 0.5)
            else:
                time.sleep(1)

    def force_block(self, duration_seconds: int, reason: str = "Manual"):
        """Force a block for a specific duration."""
        with self.lock:
            self.blocked_until = max(self.blocked_until, time.time() + duration_seconds)
            print(f"[RATE LIMIT] Forced block for {duration_seconds}s. Reason: {reason}")

    def update_from_headers(self, headers: dict, context: str = "API"):
        """
        Update the limiter state based on Meta's response headers.
        Cited: https://stackoverflow.com/questions/58931071/is-there-a-rate-limit-for-using-facebook-ad-library-api
        """
        try:
            # 1. Check X-Business-Use-Case-Usage (JSON)
            # Format: {"ads_archive":[{"type":"ads_archive","call_count":1,"total_cputime":1,"total_time":1,"estimated_time_to_regain_access":0}]}
            buc_usage = headers.get('x-business-use-case-usage') or headers.get('X-Business-Use-Case-Usage')
            if buc_usage:
                usage_data = json.loads(buc_usage)
                # Ad Library searches usually come under 'ads_archive'
                for key in usage_data:
                    for usage in usage_data[key]:
                        regain_time = usage.get('estimated_time_to_regain_access', 0)
                        if regain_time > 0:
                            with self.lock:
                                self.blocked_until = max(self.blocked_until, time.time() + (regain_time * 60) + 5)
                            print(f"[RATE LIMIT] Meta X-Business block: Wait {regain_time}m")

            # 2. Check X-Ad-Account-Usage (JSON)
            # Format: {"acc_id_util_pct": 9.67, "reset_time_duration": 120}
            acc_usage = headers.get('x-ad-account-usage') or headers.get('X-Ad-Account-Usage')
            if acc_usage:
                usage_data = json.loads(acc_usage)
                pct = usage_data.get('acc_id_util_pct', 0)
                reset_time = usage_data.get('reset_time_duration', 0)
                
                if pct >= 90: # If we are at 90% capacity, wait for reset
                    with self.lock:
                        self.blocked_until = max(self.blocked_until, time.time() + reset_time + 5)
                    print(f"[RATE LIMIT] Meta X-Account usage at {pct}%: Waiting {reset_time}s for reset")

        except Exception as e:
            # Silently fail header parsing
            pass


# Global rate limiters
openai_limiter = RateLimiter(getattr(config, 'OPENAI_RPM_LIMIT', 500))
anthropic_limiter = RateLimiter(getattr(config, 'ANTHROPIC_RPM_LIMIT', 50))
meta_limiter = MetaRateLimiter(max_score=60, window_seconds=300)

def run_multithreaded(func, items, max_workers=None, *args, **kwargs):
    """
    Run a function over a list of items using a thread pool.
    
    Args:
        func: The function to run
        items: List of items to process
        max_workers: Maximum number of threads
        *args, **kwargs: Additional arguments for the function
        
    Returns:
        List of results in the same order as items
    """
    if not items:
        return []

    if max_workers is None:
        max_workers = getattr(config, 'MAX_WORKERS', 10)

    results = [None] * len(items)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks with their index to preserve order
        future_to_index = {
            executor.submit(func, item, *args, **kwargs): i 
            for i, item in enumerate(items)
        }
        
        from concurrent.futures import as_completed
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results[index] = future.result()
            except Exception as e:
                print(f"[ERROR] Multithreaded execution failed for item {index}: {e}")
                results[index] = None
                
    return results


def run_multiprocessed(func, items, max_workers=None, *args, **kwargs):
    """
    Run a function over a list of items using a process pool (bypasses GIL).
    Ideal for CPU-bound tasks like image generation.
    """
    if not items:
        return []

    if max_workers is None:
        import os
        max_workers = os.cpu_count() or 4

    results = [None] * len(items)
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks with their index to preserve order
        future_to_index = {
            executor.submit(func, item, *args, **kwargs): i 
            for i, item in enumerate(items)
        }
        
        from concurrent.futures import as_completed
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results[index] = future.result()
            except Exception as e:
                print(f"[ERROR] Multiprocessed execution failed for item {index}: {e}")
                results[index] = None
                
    return results

