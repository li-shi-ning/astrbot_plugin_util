# import re
# import os
# import jieba
# import jieba.posseg as pseg
# from typing import List, Dict
# from astrbot.api import logger
#
# class ChineseEntityExtractor:
#     def __init__(
#             self,
#             user_dict_path: str | None = None,
#             chinese_ratio_threshold: float = 0.2
#     ):
#         """
#         初始化实体抽取器
#         """
#         jieba.initialize()
#         if user_dict_path and os.path.exists(user_dict_path):
#             self._load_dict_from_file(user_dict_path)
#         elif user_dict_path:
#             logger.error(f"警告: 词典文件不存在: {user_dict_path}")
#         self.chinese_ratio_threshold = chinese_ratio_threshold
#
#     def _load_dict_from_file(self, dict_path: str):
#         """
#         从文件读取词典并逐个添加到jieba
#         """
#         count = 0
#         with open(dict_path, 'r', encoding='utf-8') as f:
#             for line_num, line in enumerate(f, 1):
#                 line = line.strip()
#                 if not line or line.startswith('#'):
#                     continue
#                 parts = line.split()
#                 if len(parts) >= 3:
#                     word = parts[0]
#                     try:
#                         freq = int(parts[1])
#                     except ValueError:
#                         freq = 100000
#                     tag = parts[2]
#                     jieba.add_word(word, freq=freq, tag=f"nt_{tag}")
#                     count += 1
#                 else:
#                     logger.warning(f"警告: 第 {line_num} 行格式错误: {line}")
#         logger.info(f"成功从 {dict_path} 加载 {count} 个实体")
#
#     # ---------- 基础工具方法 ----------
#     @staticmethod
#     def _chinese_ratio(text: str) -> float:
#         """
#         计算文本中中文字符占比
#         """
#         if not text:
#             return 0.0
#         chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
#         return len(chinese_chars) / len(text)
#
#     @staticmethod
#     def _has_chinese(word: str) -> bool:
#         """
#         判断一个词是否包含中文字符
#         """
#         return any('\u4e00' <= ch <= '\u9fff' for ch in word)
#
#     # ---------- 动态添加实体 ----------
#     def add_entity(self, word: str, entity_type: str, freq: int = 100000):
#         """
#         动态添加一个实体到 jieba 词典中
#
#         :param word: 实体文本（必须是中文）
#         :param entity_type: 实体类型，如 person / company / location
#         :param freq: 词频，越大越容易被切出来
#         """
#         if not self._has_chinese(word):
#             return
#         flag = f"nt_{entity_type}"
#         jieba.add_word(
#             word=word,
#             freq=freq,
#             tag=flag
#         )
#
#     # ---------- 实体抽取主逻辑 ----------
#     def extract(self, text: str) -> List[Dict]:
#         """
#         从文本中抽取中文实体
#         """
#         if self._chinese_ratio(text) < self.chinese_ratio_threshold:
#             return []
#         entities = []
#         for word, flag in pseg.cut(text):
#             if not self._has_chinese(word):
#                 continue
#             if flag.startswith("nt_"):
#                 entities.append({
#                     "text": word,
#                     "type": flag.replace("nt_", "")
#                 })
#         return entities
