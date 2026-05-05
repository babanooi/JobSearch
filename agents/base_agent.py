from langchain_openai import ChatOpenAI
from setting import settings


class BaseAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model = settings.MODEL_NAME,
            openai_api_key = settings.DEEPSEEK_API_KEY,
            openai_api_base = settings.MODEL_BASE_URL,
            temperature = 0.1,
        )



    def run(self,input_content : str) ->str :
        raise NotImplementedError("子类必须实现 run 方法")
