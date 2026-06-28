import os
from PIL import Image

CACHE_DIR = os.path.join(os.getcwd(), 'cache', 'thumbnails')

class ThumbnailManager:
    '''管理 Mod 缩略图的生成和缓存'''
    def __init__(self):
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

    def get_thumbnail_path(self, package_id):
        """获取缓存文件的物理路径"""
        return os.path.join(CACHE_DIR, f"{package_id}.webp")

    def ensure_thumbnail(self, package_id, source_path):
        """
        确保缩略图存在。如果不存且源文件存在，则生成。
        :param source_path: 原始 Preview.png 的路径
        """
        target_path = self.get_thumbnail_path(package_id)
        
        # 如果缓存已存在，跳过
        if os.path.exists(target_path):
            return True
            
        if not source_path or not os.path.exists(source_path):
            return False

        try:
            with Image.open(source_path) as img:
                # 转换为 RGB (防止 PNG 透明通道在转 JPG 时报错，WEBP 支持透明但保险起见)
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new(img.mode[:-1], img.size, (0, 0, 0)) # 黑色背景
                    background.paste(img, img.split()[-1])
                    img = background
                
                # 调整大小 (64x64 足够列表用了，保持比例)
                img.thumbnail((64, 64))
                
                # 保存为 WebP (体积极小，性能好)
                img.save(target_path, 'WEBP', quality=80)
                return True
        except Exception as e:
            print(f"Failed to generate thumbnail for {package_id}: {e}")
            return False