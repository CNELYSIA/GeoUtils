# GeoUtils
 适用于GEE Python API和深度学习任务的工具集
## 简介
本模块提供了一系列工具，可实现读取、裁剪、拼接、拉伸、为影像赋予等操作。适用于处理来自GEE的64Bit色深影像和深度学习的部分预处理工作

## 核心类介绍

### ImageManager 类
- **用途**：管理图像的读取、处理（如裁剪、拼接等）、转换及保存。
- **主要方法**：
  - `readImg(strFilePath, append=False)`：从指定路径读取图像并添加到字典中。支持单个文件或整个目录的读取。
  - `saveImg(strSavePath, dictImages=None, strOutFormat='.jpg', formEE=False)`：将字典中的图像保存至指定路径，支持多种格式。
  - `cropImg(intWidth=512, intHeight=512, intStep=256, intStartGroup=1)`：对图像进行裁剪，支持设置裁剪尺寸与步长。
  - `stitchImg(intWidth=512, intHeight=512, intStep=256)`：根据裁剪参数对图像进行拼接。
  - `truncatedLinearStretch(dblPercentile=2)`：将图像数据进行百分比截断线性拉伸。
  - `assignGeoreference()`：赋予目标图像地理参考信息。

### ImageData 和 ProcessedImageData 类
- **用途**：存储图像及其相关元数据（如投影信息、地理变换矩阵等）。
    - 注意，实际使用过程中可能需要手动将数据写入属性中，通过[变量名].[属性名] = [值]即可
- **ProcessedImageData**继承自**ImageData**，额外包含处理步骤的信息。

## 使用指南

### 基本流程
1. 创建`ImageManager`实例。
2. 使用`readImg`方法加载图像。
3. 对图像进行必要的处理（如裁剪、拼接等）。
4. 使用`saveImg`方法保存结果。

### 示例代码
```python
from GeoUtils import ImageManager

# 初始化图像管理器
obj_manager = ImageManager()

# 读取图像
obj_manager.readImg('path/to/images')

# 裁剪图像
obj_manager.cropImg(intWidth=256, intHeight=256, intStep=256)

# 拼接图像
obj_manager.stitchImg(intWidth=256, intHeight=256, intStep=256)

# 保存处理后的图像
obj_manager.saveImg('./output', obj_manager.dictStitchedImages, '.jpg')
```
