from openai import OpenAI

from setting import settings

client = OpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.MODEL_BASE_URL,
)

def get_current_time() -> str:
    from datetime import datetime
    current_time = datetime.now()

    return str(current_time)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "用于查询当前系统时间",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

messages = [
    {"role": "user", "content": "现在几点了？"}
]
response = client.chat.completions.create(
    model=settings.MODEL_NAME,
    tools=tools,
    messages=messages
)

msg = response.choices[0].message
#如果模型回复中包含调用工具的请求
if msg.tool_calls:
    #获取模型想要调用的工具的名称
    tool_calls = msg.tool_calls[0].function.name
    #如果是get_current_time
    if tool_calls == "get_current_time":
      tool_result = get_current_time()
    messages.append(msg.model_dump())  #model_dump() 是 OpenAI SDK 提供的方法，它会把这个对象转换成一个标准的 Python 字典
    messages.append(
        {
            "role": "tool",
            "content": tool_result,
            "tool_call_id": msg.tool_calls[0].id #让模型知道这是刚刚调用工具请求的回复
        }
    )
    final_res = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=messages
    )
    print("最终回答：", final_res.choices[0].message.content)


