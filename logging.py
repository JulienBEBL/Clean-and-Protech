import os
import logging
from datetime import datetime

def setup_logging(log_dir="logs"):
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(log_dir, f"{timestamp}.log")
    
    logging.basicConfig(
        filename=log_file, 
        level=logging.INFO, 
        format="%(asctime)s;%(message)s"
    )
    
    return logging.getLogger("irrigation_control")
