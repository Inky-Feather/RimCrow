import ast
import os
import re
import subprocess
import sys
from typing import Callable, Optional

def packApplication(main_file="main.py", icon_path="", name=""):
    """
    使用 PyInstaller 打包应用程序
    
    Args:
        main_file (str): 主程序文件路径
        icon_path (str): 图标文件路径
        name (str): 程序名称
    """
    try:
        # 确保文件存在
        if not os.path.exists(main_file):
            raise FileNotFoundError(f"主程序文件 '{main_file}' 不存在")
        
        if not os.path.exists(icon_path):
            raise FileNotFoundError(f"图标文件 '{icon_path}' 不存在")
            
        # 构建 PyInstaller 命令
        cmd = [
            "uv","run",     # 使用uv运行pyinstaller
            "pyinstaller",
            "-F",  # 打包成单个文件
            # "-D",  # 打包成目录
            "-w",  # 无控制台窗口
            "--noconfirm",  # 跳过确认提示
            "--contents-directory", "lib",
            "--add-data","frontend/dist:frontend/dist",
            "--collect-binaries","steamworks",
            "--clean",  # 清理旧构建文件
            "--upx-dir", r"D:\Environment\upx-5.0.0-win64",  # 指定 UPX 路径
            "-i", icon_path,  # 指定图标
            "-n", name,  # 指定名称
            main_file  # 主程序文件
        ]
        
        # 执行打包命令
        # result = subprocess.run(cmd, capture_output=True, text=True)
        result = subprocess.run(cmd, text=True)
        
        if result.returncode == 0:
            print("打包成功！")
            print(f"输出目录: {os.path.abspath('dist')}")
        else:
            print("打包失败！")
            print("错误信息：")
            print(result.stderr)
            
    except Exception as e:
        print(f"打包过程中出错: {str(e)}")
        sys.exit(1)

# 目录树结构
def filestree(path='.', exclude:list[str]=None, ignore='', max_depth:int=None, filter_func:Optional[Callable[[str], bool]]=None, # type: ignore
              indent=2,branch_indent:int=None,sub_indent:int=None, # type: ignore
              branch_sign='·[',branch_sign_end=']',leaf_sign=' ',leaf_sign_end=''):
    if not path or not os.path.isdir(path): return '路径错误！' # 忽略错误地址
    if exclude is None: exclude = []
    if filter_func is None: filter_func = lambda x: True  # 过滤函数默认正确
    ignore_pattern = re.compile(ignore) if ignore else None # 正则表达式默认
    # 本质为先叠加后替换，先复制父级前缀，再将尾端分支符号替换为无分支的插入符号
    if indent==None: indent=2   # 通用缩进处理
    if indent!=None: branch_indent_=sub_indent_=indent
    if branch_indent!=None: branch_indent_=branch_indent    # 细节缩进优先级更高
    if sub_indent!=None: sub_indent_=sub_indent
    branch_sign = branch_sign or '' # 文件夹标记
    branch_sign_end = branch_sign_end or ''
    leaf_sign = leaf_sign or '' # 文件标记
    leaf_sign_end = leaf_sign_end or ''
    branch_mid = '├' + '─'*branch_indent_
    branch_end = '└' + '─'*branch_indent_
    sub_insert_mid = '│' + ' '*sub_indent_
    sub_insert_end = ' ' + ' '*sub_indent_
    treestr = [branch_sign + os.path.basename(path)+branch_sign_end]  # 结果列表
    # 读取目录内文件，输出按类型排序后的列表 [[地址，前缀符号，深度],……]
    def process_path(path, files, prefix='', depth=0):
        pathlist = []
        for item in files:
            # 过滤设置
            if item in exclude: continue # 排除项过滤
            if not filter_func(item): continue  # 函数过滤
            if ignore_pattern and ignore_pattern.match(item): continue   # 正则过滤
            item_path = os.path.join(path, item)    # 获取文件地址
            pathlist.append([item_path,prefix+branch_mid,depth])    # 添加到结果列表[地址，前缀符号，深度]
        # 按类型排序文件
        pathlist = sorted(pathlist, key=lambda x: (
            not os.path.isdir(x[0]),  # 文件夹在前（False < True）
            os.path.splitext(x[0])[1] if os.path.isfile(x[0]) else '',  # 按扩展名排序
            os.path.basename(x[0])  # 按文件名排序（如果扩展名相同）
        ))
        if pathlist: pathlist[-1][1] = prefix+branch_end   # 修改最后项的前缀
        
        return pathlist[::-1]   # 返回反序列表（pop()会逆序处理）
    
    # 添加结果到任务序列
    worklist = process_path(path,os.listdir(path))
    while worklist:
        item_path,prefix,depth = worklist.pop()
        name = os.path.basename(item_path)   # 输出行=前缀+文件名
        add = sub_insert_mid if prefix.endswith(branch_mid) else sub_insert_end    # 前缀处理，判断父级是否在中间分支
        if os.path.isdir(item_path):
            # treestr.append(prefix[:-len(branch_mid)]+sub_insert_mid) # 目录前空一行
            if max_depth and depth+1>=max_depth:continue    # 深度过滤
            worklist.extend(process_path(item_path,os.listdir(item_path),prefix[:-len(branch_mid)]+add,depth+1))
            line = prefix + branch_sign + name + branch_sign_end # 文件夹标记
        else:
            line = prefix + leaf_sign + name + leaf_sign_end    # 文件标记
        treestr.append(line)
        if add==sub_insert_end: treestr.append(prefix[:-len(branch_mid)]+sub_insert_end) # 分支结束后空一行
    
    return "\n".join(treestr)   # 合并结果行

    

if __name__ == "__main__":
    # 执行打包
    main_file = 'main.py'
    icon_path = 'icon.ico'
    print('开始打包')
    packApplication(main_file, icon_path, 'RimModManager')
    print('生成目录结构')
    p = r'.'
    tree = filestree(p, exclude=['__pycache__','__init__.py','build','old','cache','node_modules','dist','data','backups','public','assets','temp','test','tools'],ignore=r'^\.')
    with open('files_tree.txt','w',encoding='utf-8') as n:
        n.write(tree)
    print('生成完毕')
    
    