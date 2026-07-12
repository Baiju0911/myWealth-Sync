import math
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


def run_in_parallel(payload_list, worker_func, extra_args=None, max_workers=4):
    """
    ⚡ GENERIC PARALLEL THREADPOOL UTILITY (O(1) INTERCEPT STRATEGY)
    Abstracts batch execution flows by routing chunk arrays through an executor.map stream.
    """
    total_items = len(payload_list)
    if total_items == 0:
        return []

    if extra_args is None:
        extra_args = ()
    elif not isinstance(extra_args, tuple):
        extra_args = (extra_args,)

    chunk_size = math.ceil(total_items / max_workers)
    chunks = [
        payload_list[i : i + chunk_size] for i in range(0, total_items, chunk_size)
    ]

    aggregated_results = []

    # 🚀 STREAM INTERCEPT DESK: Maps full data slices to structural threads simultaneously
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        try:
            # We use a clean inline lambda structure to bind our lookups into the worker target map
            results = executor.map(
                lambda chunk: worker_func(chunk, *extra_args), chunks
            )

            # Collect payloads sequentially as execution loops settle out
            for result in results:
                if result is not None:
                    aggregated_results.append(result)

        except Exception as e:
            logger.error(
                f"❌ Parallel execution failed inside mapper track: {str(e)}",
                exc_info=True,
            )
            raise e

    return aggregated_results


# def run_in_parallel1(payload_list, worker_func, extra_args=None, max_workers=4):

#     total_items = len(payload_list)
#     if total_items == 0:
#         return []

#     # Enforce clean formatting bounds for auxiliary variables
#     if extra_args is None:
#         extra_args = ()
#     elif not isinstance(extra_args, tuple):
#         extra_args = (extra_args,)

#     # Calculate optimal workload balance per chunk frame
#     chunk_size = math.ceil(total_items / max_workers)
#     chunks = [
#         payload_list[i : i + chunk_size] for i in range(0, total_items, chunk_size)
#     ]

#     logger.info(
#         f"🚀 Parallel Engine spawning {len(chunks)} threads across {total_items} items."
#     )

#     aggregated_results = []

#     # Deploy worker threads in isolated sandboxes bypassing connection conflicts
#     with ThreadPoolExecutor(max_workers=max_workers) as executor:
#         # Schedule chunks with unpacking for the extra parameters safely appended
#         futures = [executor.submit(worker_func, chunk, *extra_args) for chunk in chunks]

#         # Collect returning artifacts as they finish execution
#         for future in futures:
#             try:
#                 result = future.result()
#                 if result is not None:
#                     aggregated_results.append(result)
#             except Exception as e:
#                 logger.error(
#                     f"❌ Worker thread execution failed: {str(e)}", exc_info=True
#                 )
#                 raise e

#     return aggregated_results
