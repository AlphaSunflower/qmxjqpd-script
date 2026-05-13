from core.strategies.dynasty_55 import Dynasty55Strategy
from core.strategies.dynasty_33 import Dynasty33Strategy
from core.strategies.chaolian_front import ChaolianFrontStrategy
from core.strategies.chaolian_challenge import ChaolianChallengeStrategy
from core.strategies.chaolian_step import ChaolianStepStrategy
from core.strategies.dynasty_all import DynastyAll
from core.strategies.full_auto import FullAutoTaskStrategy
# 注册模式后要写入此文件
STRATEGY_MAP = {
    "dynasty_55": Dynasty55Strategy,
    "dynasty_33": Dynasty33Strategy,
    "chaolian_front": ChaolianFrontStrategy,
    "chaolian_challenge": ChaolianChallengeStrategy,
    "chaolian_step": ChaolianStepStrategy,
    "dynasty_all": DynastyAll,
    "full_auto": FullAutoTaskStrategy,
}

__all__ = [
    "Dynasty55Strategy",
    "Dynasty33Strategy",
    "ChaolianFrontStrategy",
    "ChaolianChallengeStrategy",
    "ChaolianStepStrategy",
    "STRATEGY_MAP",
    "DynastyAll",
    "FullAutoTaskStrategy",
]
