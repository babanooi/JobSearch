from openai import OpenAI
from tavily import TavilyClient

from setting import settings

client = OpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.MODEL_BASE_URL,
)

tavily = TavilyClient(
    api_key=settings.TAVILY_API_KEY,
)

react_prompt = """
你必须严格按照格式执行：
1. 先思考：Thought=你当前需要做什么
2. 如果需要联网实时信息：Action=search，ActionInput=搜索关键词
3. 如果信息足够回答：Action=finish，ActionInput=最终答案
用户问题：{question}
"""

def react_run(question:str):
    messages = [
        {
            "role":"user","content":react_prompt.format(question=question),
        }
    ]
    while True:
        res = client.chat.completions.create(model = settings.MODEL_NAME,messages=messages,temperature=0)
        content = res.choices[0].message.content
        print("===AI思考===\n", content)

        if "Action=search" in content:
            search_key = content.split("ActionInput=")[-1].strip()
            search_result = tavily.search(search_key)   #tavili返回的是一个字典对象
            context = f"{search_result["results"][0]["content"]}"
            message = messages.append(
                {
                  "role":"assistant","content":context
                }
            )
        elif "Action=finish" in content:
            return content.split("ActionInput=")[-1].strip()

if __name__ == "__main__":
  res = react_run("今天杭州天气怎么样")
  print(res)



