# 焦点堆叠批量处理工具

面向产品摄影的本地焦点堆叠工具。它可以扫描一个文件夹中的包围对焦照片，自动分组、对齐并融合，再批量输出全清晰图片。

图片只在你的电脑上处理，不会上传网络。网页服务默认只监听 `127.0.0.1`，同一局域网内的其他设备无法访问。

## 功能

- 支持 JPG、JPEG、PNG、TIF、TIFF、BMP、WebP 以及常见相机 RAW 格式。
- 按拍摄时间间隔识别连续拍摄组，并用“每组最多张数”避免相邻产品被合并。
- 使用多尺度 ECC 对齐、Laplacian 清晰度检测和软掩码融合。
- 可选镜头畸变与色差矫正。
- 批量输出 JPG、PNG 或 TIF。
- 处理进度、成功数量和错误信息会显示在网页中。

## Windows 快速开始

1. 安装 [Python 3.10 或更高版本](https://www.python.org/downloads/)，安装时勾选 `Add Python to PATH`。
2. 下载并解压本项目。
3. 双击 `启动工具_Windows.bat`。
4. 首次启动会安装依赖，完成后浏览器自动打开 <http://127.0.0.1:5050>。
5. 关闭命令窗口即可停止工具。

## macOS 快速开始

在终端进入项目目录并运行：

```bash
chmod +x 启动工具_Mac.sh
./启动工具_Mac.sh
```

## 使用步骤

1. 在资源管理器或访达中复制待处理图片文件夹的完整路径。
2. 粘贴到“输入文件夹路径”。输出路径可留空，程序会创建“输出”文件夹。
3. 设置每组最多张数。若每个产品通常拍摄 10 张，就填写 `10`。
4. 点击“预览分组”，确认每组照片属于同一产品。
5. 选择格式和质量，再点击“开始处理”。

## 分组规则

程序读取图片的 EXIF 拍摄时间；没有 EXIF 时使用文件修改时间。它会根据相邻照片的时间间隔自动切组。若一个时间组超过“每组最多张数”，则再按该数量顺序拆分。

因此，批量处理前应先查看分组预览。不同产品之间最好停顿几秒，识别会更稳定。

## 依赖与 RAW 支持

基础依赖记录在 `requirements.txt`。`rawpy` 用于读取相机 RAW 文件，`lensfunpy` 用于镜头数据库矫正。若这两个可选组件安装失败，JPG、PNG 和 TIF 仍可处理，页面顶部会显示组件状态。

## 文件结构

```text
focus-stacking-batch-processor/
├─ static/index.html       网页界面
├─ tests/test_server.py    基础接口测试
├─ focus_stack_engine.py   图像处理核心
├─ server.py               本机网页服务
├─ requirements.txt        Python 依赖
├─ 启动工具_Windows.bat
└─ 启动工具_Mac.sh
```

## 手动启动与测试

```bash
python -m pip install -r requirements.txt
python server.py
```

运行基础测试：

```bash
python -m unittest discover -s tests -v
```

## 注意事项

- 第一次请用图片副本试跑，确认分组和输出符合预期后再批量处理。
- RAW 文件会占用较多内存；每组张数越多，处理需要的内存越大。
- 请勿把输出文件夹设置为包含唯一原片的目录，建议始终单独输出。

## 许可证

本项目采用 [MIT License](LICENSE)。
