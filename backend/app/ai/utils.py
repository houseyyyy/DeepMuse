import time
from functools import wraps

def retry(max_retries=3, delay=2, allowed_exceptions=()):
    """
    一个装饰器, 用于重试一个函数, 如果它抛出一个异常.

    :param max_retries: 最大重试次数, 默认为3.
    :param delay: 重试之间的延迟时间, 默认为2秒.
    :param allowed_exceptions: 允许触发重试的异常类型元组, 默认为空元组.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # 如果指定了允许的异常, 只重试这些异常
                    if allowed_exceptions and not isinstance(e, allowed_exceptions):
                        raise  # 如果不在允许的异常列表中, 重新抛出异常

                    attempts += 1
                    if attempts >= max_retries:
                        print(
                            f"Function '{func.__name__}' failed after {max_retries} attempts. Re-raising last exception."
                        )
                        raise e

                    print(
                        f"Attempt {attempts}/{max_retries} for '{func.__name__}' failed with error: {e}. Retrying in {delay} seconds..."
                    )
                    time.sleep(delay)
        return wrapper
    return decorator 
