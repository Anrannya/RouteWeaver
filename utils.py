import json
import logging
import math
import os
import random
import sys

import openai
from openai import OpenAI

# 各模型 API 单价, 单位: 美元 / 1M tokens。
# DeepSeek 为官方永久价(2026-05 起): 输入区分缓存命中(prompt_cache_hit)与未命中(prompt)。
# GPT 系列沿用原有计费方式(无缓存分层)。本地模型(llama 等)不在表中, 计费为 0。
MODEL_PRICES_PER_1M = {
    "gpt-4-turbo": {"prompt": 10, "completion": 30},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.6},
    "gpt-3.5-turbo": {"prompt": 0.5, "completion": 1.5},
    "gpt-4": {"prompt": 30, "completion": 60},
    "gpt-4o": {"prompt": 2.5, "completion": 10},
    "deepseek-v4-pro": {"prompt": 0.435, "prompt_cache_hit": 0.003625, "completion": 0.87},
    "deepseek-v4-flash": {"prompt": 0.14, "prompt_cache_hit": 0.0028, "completion": 0.28},
}


def askChatGPT(messages, model="deepseek-v4-pro", temperature = 1, max_tokens=10000):
    response = openai.ChatCompletion.create(
            model = model,
            messages = messages,
            temperature = temperature,
            max_tokens = max_tokens,
            extra_body={
                     "thinking": {
                            "type": "disabled"
                     }
                },
        )
    addtoken(response.usage.total_tokens)
    answer = response.choices[0].message["content"]
    return answer.strip()


def askLLM(clients, messages, tokens_path, model="deepseek-v4-pro", temperature = 1, max_tokens=10000):
    # 需要包括DeepSeek系列以及LLaMA系列的模型调用,分开写已备调用接口略有区别
    
    if model in ['gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo', 'gpt-4o-mini', 'gpt-4o', 'deepseek-v4-pro', 'deepseek-v4-flash']: # DeepSeek系列模型调用           
        client = clients['gpt']  # deepseek系列共用一个client
        response = client.chat.completions.create(
                model = model,
                messages = messages,
                temperature = temperature,
                max_tokens = max_tokens,
                extra_body={
                     "thinking": {
                            "type": "disabled"
                     }
                },
            )
        record_usage(model, response.usage, tokens_path)
        answer = response.choices[0].message.content
        
    elif model in ['llama3-70b', 'llama3-8b', 'llama3:8b']:
        client = clients['llama']  # llama系列共用一个client
        response = client.chat.completions.create(
                model = model, 
                messages = messages,
                temperature = temperature,
                max_tokens = max_tokens,
            )
        answer = response.choices[0].message.content
    else:
        print('MODEL error')
        print(model)
        sys.exit(0)

    return answer.strip()



def askLLM_withprob(clients, messages, tokens_path, model="deepseek-v4-pro", temperature = 1, max_tokens=10000):
    # 需要包括DeepSeek系列以及LLaMA系列的模型调用,调用接口略有区别
    probs = {}
    if model in ['gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo', 'gpt-4o-mini', 'deepseek-v4-pro', 'deepseek-v4-flash']: # DeepSeek系列模型调用           
        client = clients['gpt']  # deepseek系列共用一个client
        response = client.chat.completions.create(
                model = model,
                messages = messages,
                temperature = temperature,
                max_tokens = max_tokens,
                extra_body={
                     "thinking": {
                            "type": "disabled"
                     }
                },
                logprobs = True,
            )
        record_usage(model, response.usage, tokens_path)
        answer = response.choices[0].message.content
        for item in response.choices[0].logprobs.content:
            # 在这一步就把logprob用e指数返回成prob
            probs[item.token] = math.exp(item.logprob)
        
    elif model in ['llama3-70b', 'llama3-8b', 'llama3:8b']:
        client = clients['gpt']  # 这里需要改成llama系列的prompts  # TODO 还没拿到LLaMA的key, 所以先拿deepseek充当.
        response = client.chat.completions.create(
                model = model,  # TODO 还没拿到LLaMA的key, 所以先拿deepseek充当.
                messages = messages,
                temperature = temperature,
                max_tokens = max_tokens,
                logprobs = True,
            )
        record_usage("deepseek-v4-pro", response.usage, tokens_path)
        answer = response.choices[0].message.content
        for item in response.choices[0].logprobs.content:
            probs[item.token] = math.exp(item.logprob)
    else:
        print('MODEL error')
        print(model)
        sys.exit(0)

    return answer.strip(), probs



def update_token_usage(model_name, prompt_tokens, completion_tokens,
                       file_path='token_usage.json', prompt_cache_hit_tokens=0):
    """按模型累计 token 用量。prompt_cache_hit_tokens 是 prompt_tokens 中命中缓存的部分(DeepSeek 计费更低)。"""
    with open(file_path, 'r') as f:
        data = json.load(f)

    entry = data.setdefault(model_name, {
        'prompt_tokens': 0,
        'prompt_cache_hit_tokens': 0,
        'completion_tokens': 0,
        'total_tokens': 0
    })

    entry['prompt_tokens'] += prompt_tokens
    entry['prompt_cache_hit_tokens'] = entry.get('prompt_cache_hit_tokens', 0) + prompt_cache_hit_tokens
    entry['completion_tokens'] += completion_tokens
    entry['total_tokens'] += (prompt_tokens + completion_tokens)

    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)


def record_usage(model_name, usage, tokens_path):
    """从 API response.usage 中读取真实 token 数并按真实模型名记账。

    DeepSeek 的 usage 额外返回 prompt_cache_hit_tokens(缓存命中输入), 记录下来供
    CountCost 按官方 缓存命中/未命中 两档价格计算真实开销; 其他模型该字段为 0。
    """
    cache_hit = getattr(usage, 'prompt_cache_hit_tokens', 0) or 0
    update_token_usage(model_name, usage.prompt_tokens, usage.completion_tokens,
                       file_path=tokens_path, prompt_cache_hit_tokens=cache_hit)

 
def addtoken(num):
    try:
        with open("tokens.txt", "r") as f:
            data = f.read()
            nownum = int(data)        
            
        if num == -1:
            nownum = 0
        else:
            nownum = nownum + num
        
        with open("tokens.txt","w+") as f:
            f.write(str(nownum))
    except:
        pass

    
def _load_dotenv(path):
    """从 KEY=VALUE 文件加载环境变量（不覆盖已存在的 env）。"""
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key, val = key.strip(), val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


def _resolve_deepseek_api_key():
    """优先读已 export 的环境变量；否则尝试项目内 .env（不覆盖已有 env）。"""
    key = (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if key:
        return key
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in (".env", "../.env", "MATH_Trys/.env", "CSQA_Trys/.env"):
        _load_dotenv(os.path.normpath(os.path.join(here, rel)))
    return (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()


def setOpenAi(keyid = 0):
    # set your deepseek key here.
    base_url = "https://api.deepseek.com"
    api_key = _resolve_deepseek_api_key()
    if not api_key:
        raise RuntimeError(
            "未找到 DeepSeek API Key。请在运行前执行：\n"
            "  export DEEPSEEK_API_KEY='sk-...'\n"
            "或在 DoT/DoT/.env 中写入：DEEPSEEK_API_KEY=sk-...\n"
            "（也支持 OPENAI_API_KEY；当前 shell 中两者均未设置）"
        )
    client = OpenAI(base_url=base_url, api_key=api_key)
    addtoken(-1)
    return client

def setLocal():
    client = OpenAI(
        api_key="ollama",
        base_url="http://localhost:11434/v1",
    )
    return client

def printSeq(seq):
    for item in seq:
        print(item)

def judgeNum(num1, num2):
    num1 = num1.replace(',', '')
    num2 = num2.replace(',', '')
    num1 = int(num1)
    num2 = int(num2)
    return 1 if num1 == num2 else 0


def reverseDict(original_dict):
    reversed_dict = {}

    # 遍历原始字典的键值对
    for key, value in original_dict.items():
        if value in reversed_dict:
            reversed_dict[value].append(key)
        else:
            reversed_dict[value] = [key]
    return reversed_dict

def search_Predecessors(edges, id):
    res = []
    for edge in edges:
        if edge[1] == id:
            res.append(edge[0])
    return res

def setup_logger(tailName=""):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Create handlers
    c_handler = logging.StreamHandler(sys.stdout)
    f_handler = logging.FileHandler("Logs/test_"+tailName+".log")

    # Add handlers to the logger
    logger.addHandler(c_handler)
    logger.addHandler(f_handler)

    return logger, "test_"+tailName+".log"

def CountCost(token_usage):
    """根据累计 token 用量计算 (总token数, 总成本/美元)。

    价格表见 MODEL_PRICES_PER_1M。对带缓存分层的模型(DeepSeek), 输入按
    缓存命中/未命中 两档分别计价; 无价格记录的模型(如本地 llama)按 0 计费。
    """
    total_tokens = 0
    total_cost = 0.0

    for model, tokens in token_usage.items():
        prompt_tokens = tokens['prompt_tokens']
        completion_tokens = tokens['completion_tokens']
        cache_hit_tokens = min(tokens.get('prompt_cache_hit_tokens', 0), prompt_tokens)
        total_tokens += prompt_tokens + completion_tokens

        price = MODEL_PRICES_PER_1M.get(model)
        if price is None:
            continue  # 本地/未知模型不计费
        hit_price = price.get('prompt_cache_hit', price['prompt'])
        total_cost += (cache_hit_tokens / 1e6) * hit_price
        total_cost += ((prompt_tokens - cache_hit_tokens) / 1e6) * price['prompt']
        total_cost += (completion_tokens / 1e6) * price['completion']

    return total_tokens, total_cost


def seconds_to_hms(seconds):
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    return hours, minutes, seconds


def quantile(lst, alpha):
    # 确保 alpha 在 0 和 1 之间
    if not 0 <= alpha <= 1:
        raise ValueError("alpha should be between 0 and 1")

    # 排序列表
    sorted_lst = sorted(lst)

    # 计算分位数的索引
    index = int(alpha * len(sorted_lst))

    # 如果索引等于列表长度，返回最后一个元素
    if index == len(sorted_lst):
        index -= 1

    # 返回分位数的值
    return sorted_lst[index]


def upGradeModel(modelName):
    # gpt-4o-mini, gpt-3.5-turbo, llama3-70b, llama3-8b
    if modelName == 'llama3-8b':
        return 'llama3-70b'
    elif modelName == 'llama3-70b':
        return 'gpt-3.5-turbo'
    elif modelName == 'gpt-3.5-turbo':
        return 'gpt-4o-mini'
    if modelName == 'gpt-4o-mini':
        return 'gpt-4'
    elif modelName == 'gpt-4':
        return 'gpt-4-turbo'
    elif modelName == 'gpt-4-turbo':
        return 'gpt-4-turbo'
        
def allbest_allocation(n):
    selection = {i + 1: 'gpt-4-turbo' for i in range(n)}
    return selection

def random_model_selection(n):
    models = ['gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo', 'gpt-4o-mini', 'llama3-70b', 'llama3-8b']
    selection = {i + 1: random.choice(models) for i in range(n)}
    return selection

def check_and_create_json_file(file_path):
    # 判断文件是否存在
    if not os.path.exists(file_path):
        # 如果文件不存在，创建一个新文件并写入空的 JSON 结构
        with open(file_path, 'w') as f:
            json.dump({}, f)  # 初始化一个空的 JSON 对象
        # print(f"{file_path} 文件不存在，已创建新文件。")
    else:
        # print(f"{file_path} 文件已存在。")
        pass


def check_and_create_txt_file(file_path):
    # 判断文件是否存在
    if not os.path.exists(file_path):
        # 如果文件不存在，创建一个新文件
        with open(file_path, 'w') as f:
            f.write('')  # 写入空内容创建文件
        # print(f"{file_path} 文件不存在，已创建新文件。")
        return False
    else:
        # print(f"{file_path} 文件已存在。")
        if os.path.getsize(file_path) > 0:
            return True
        else:
            return False
        
        
# 定义模型和数字的映射
model_mapping = {
    'gpt-4-turbo': 5,
    'gpt-4': 4,
    'gpt-4o-mini': 3,
    'gpt-3.5-turbo': 2,
    'llama3-70b': 1,
    'llama3-8b': 0
}

def downgrading_vanilla(original_dict):
    # 第一步：转换value为映射后的数字
    reverse_mapping = {v: k for k, v in model_mapping.items()}  # 创建反向映射
    converted_dict = {k: model_mapping[v] for k, v in original_dict.items()}

    # 筛选出值大于 0 的键
    keys_above_min = [k for k, v in converted_dict.items() if v > 0]
    if len(keys_above_min)==0:
        return False
        
    # 如果存在大于 0 的值
    if keys_above_min:
        # 随机选择 1-3 个键
        num_keys_to_decrement = random.choice([1, 2])
        keys_to_decrement = random.sample(keys_above_min, min(num_keys_to_decrement, len(keys_above_min)))

        # 将选中的键对应的值减 1
        for key in keys_to_decrement:
            converted_dict[key] -= 1

    # 第三步：将数字转换回模型名称
    final_dict = {k: reverse_mapping[v] for k, v in converted_dict.items()}

    return final_dict


def downgrading_pro(original_dict):
    # 第一步：转换value为映射后的数字
    reverse_mapping = {v: k for k, v in model_mapping.items()}  # 创建反向映射
    converted_dict = {k: model_mapping[v] for k, v in original_dict.items()}

    # 筛选出值大于 0 的键
    keys_above_min = [k for k, v in converted_dict.items() if v > 1]
    if len(keys_above_min)==0:
        return False
        
    # 如果存在大于 0 的值
    if keys_above_min:
        # 随机选择 1-3 个键
        num_keys_to_decrement = random.choice([2, 3, 4])
        keys_to_decrement = random.sample(keys_above_min, min(num_keys_to_decrement, len(keys_above_min)))

        # 将选中的键对应的值减 2
        for key in keys_to_decrement:
            converted_dict[key] -= 2

    # 第三步：将数字转换回模型名称
    final_dict = {k: reverse_mapping[v] for k, v in converted_dict.items()}

    return final_dict


def downgrading_promax(original_dict):
    # 第一步：转换value为映射后的数字
    reverse_mapping = {v: k for k, v in model_mapping.items()}  # 创建反向映射
    converted_dict = {k: model_mapping[v] for k, v in original_dict.items()}

    # 筛选出值大于 0 的键
    keys_above_min = [k for k, v in converted_dict.items() if v > 0]
    if len(keys_above_min)==0:
        return False
        
    # 如果存在大于 0 的值
    if keys_above_min:
        # 随机选择 1-3 个键
        num_keys_to_decrement = random.choice([2, 3, 4])
        keys_to_decrement = random.sample(keys_above_min, min(num_keys_to_decrement, len(keys_above_min)))

        # 将选中的键对应的值减 1
        for key in keys_to_decrement:
            converted_dict[key] -= 1

    # 第三步：将数字转换回模型名称
    final_dict = {k: reverse_mapping[v] for k, v in converted_dict.items()}

    return final_dict


def upgrading(original_dict):
    # 第一步：转换value为映射后的数字
    reverse_mapping = {v: k for k, v in model_mapping.items()}  # 创建反向映射
    converted_dict = {k: model_mapping[v] for k, v in original_dict.items()}

    # 筛选出值小于 5 的键
    keys_below_max = [k for k, v in converted_dict.items() if v < 5]

    # 如果存在小于 5 的值
    if keys_below_max:
        # 随机选择 1-2 个键
        num_keys_to_increment = random.choice([1, 2])
        keys_to_increment = random.sample(keys_below_max, min(num_keys_to_increment, len(keys_below_max)))

        # 将选中的键对应的值加 1
        for key in keys_to_increment:
            converted_dict[key] += 1

    # 第三步：将数字转换回模型名称
    final_dict = {k: reverse_mapping[v] for k, v in converted_dict.items()}

    return final_dict


# 定义将数据写入JSON文件的函数
def write_json(file_path, data):
    try:
        # 打开文件并写入数据，确保格式化输出
        # 主义是覆盖写入,每次写入会刷掉之前的格式
        with open(file_path, 'w', encoding='utf-8') as f:  
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"数据成功写入 {file_path}")
    except Exception as e:
        print(f"发生错误：{e}")
        
        
def write_json_listoneline(file_path, data):
    try:
        # 自定义递归函数，用于处理 list 和其他类型的数据
        def custom_json_encoder(obj, indent=0):
            # 定义缩进
            indent_str = ' ' * indent
            
            if isinstance(obj, dict):
                # 处理 dict 类型
                json_str = '{\n'
                for i, (key, value) in enumerate(obj.items()):
                    if i > 0:
                        json_str += ',\n'
                    json_str += f'{indent_str}  "{key}": {custom_json_encoder(value, indent + 2)}'
                json_str += f'\n{indent_str}}}'
                return json_str

            elif isinstance(obj, list):
                # 处理 list 类型，不换行
                return json.dumps(obj, separators=(',', ':'))

            else:
                # 处理其他类型
                return json.dumps(obj, ensure_ascii=False)

        # 打开文件并写入数据
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(custom_json_encoder(data))
        
        print(f"数据成功写入 {file_path}")
    except Exception as e:
        print(f"发生错误：{e}")


def extract_numbers_from_filenames(folder_path):
    numbers = []
    # 遍历文件夹中的所有文件
    for file_name in os.listdir(folder_path):
        if file_name.endswith('.json'):
            # 提取文件名中的数字部分并转换为整数
            number = int(file_name.split('.')[0])
            numbers.append(number)
    return numbers


def sort_with_indices(input_list):
    # 使用enumerate为每个元素加上原始索引，然后根据值进行排序
    sorted_indices = sorted(range(len(input_list)), key=lambda k: input_list[k], reverse=True)
    sorted_list = [input_list[i] for i in sorted_indices]  # 根据排序后的索引生成排序后的列表
    return sorted_list, sorted_indices


def find_first_valid_key(lst, dictx):
    for key in lst:
        if dictx.get(key) == 'gpt-4-turbo':  # 检查key在dictx中的值
            return key
    return None  # 如果没有找到符合条件的返回None


def find_first_valid_key2(lst, dictx):
    for key in reversed(lst):
        if dictx.get(key) == 'llama3-8b':  # 检查key在dictx中的值
            return key
    return None  # 如果没有找到符合条件的返回None

if __name__ == '__main__':
    lst = [1,2,3,4,5,6,7,8,9,10]
    print(quantile(lst, 0.2)) 
