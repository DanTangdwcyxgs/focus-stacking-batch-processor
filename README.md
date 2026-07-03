# 焦点堆叠批量处理工具
## Focus Stacking Batch Processor

专为产品摄影（眼镜等）设计的全自动焦点堆叠批量处理工具。

---

## 快速开始

### Mac 用户
双击 `启动工具_Mac.sh`，或终端运行：
```bash
chmod +x 启动工具_Mac.sh
./启动工具_Mac.sh
```

### Windows 用户
双击 `启动工具_Windows.bat`

启动后浏览器会自动打开 **http://localhost:5050**

---

## 使用方法

1. **输入文件夹路径**：填入包含所有图片的文件夹路径
2. **设置每组张数**：一般填 10（你的焦点包围数量）
3. **选择输出格式**：JPG（文件小）/ PNG（无损）/ TIF（印刷级）
4. **点击「预览分组」**：先看看自动分组是否正确
5. **点击「开始批量处理」**：坐等结果 ☕

---

## 自动分组算法

程序按以下优先级自动识别哪些图片属于同一产品：

1. **文件名序列号**：如 `IMG_001~010` 为一组，`IMG_011~020` 为另一组
2. **EXIF 时间戳**：根据拍摄时间间隔自动聚类
3. **顺序分组**：按你设置的每组张数平均分配

---

## 处理流程

```
输入300张 → 自动分组(30组×10张) → 每组:
  1. ECC 图像对齐（消除拍摄抖动）
  2. Laplacian 清晰度计算（识别每张最清晰区域）
  3. 软掩码焦点融合（平滑拼接过渡）
  → 输出1张全清晰合成图

最终：300张 → 30张全清晰结果图
```

---

## 支持格式

输入：JPG · JPEG · PNG · TIF · TIFF · BMP · WebP · CR2 · NEF · ARW

输出：JPG · PNG · TIF

---

## 依赖

首次启动会自动安装：
- opencv-python-headless（图像处理）
- numpy（数值计算）
- flask（Web界面）
- pillow（图像读写）
- scikit-image（图像对齐辅助）

---

## 文件说明

```
focus_stack/
├── server.py              # Web服务器
├── focus_stack_engine.py  # 核心算法引擎
├── static/
│   └── index.html         # Web界面
├── 启动工具_Mac.sh
├── 启动工具_Windows.bat
└── README.md
```
