# pytest 配置：从项目根导入 app
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
