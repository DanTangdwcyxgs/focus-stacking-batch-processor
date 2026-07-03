"""
Focus Stacking Engine v6
修复 RAF 模糊问题：多分辨率对齐 + 自适应block_size + RAW锐化
"""

import cv2
import numpy as np
import os, re, time
from pathlib import Path
from PIL import Image
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import multiprocessing

def get_optimal_workers():
    cores = multiprocessing.cpu_count()
    return max(1, min(cores - 2, 6))

OPTIMAL_WORKERS = get_optimal_workers()

try:
    import rawpy
    HAS_RAWPY = True
except ImportError:
    HAS_RAWPY = False

try:
    import lensfunpy
    HAS_LENSFUN = True
except ImportError:
    HAS_LENSFUN = False

RAF_EXTS    = {'.raf','.cr2','.cr3','.nef','.arw','.dng','.rw2','.orf'}
NORMAL_EXTS = {'.jpg','.jpeg','.png','.tif','.tiff','.bmp','.webp'}
ALL_EXTS    = RAF_EXTS | NORMAL_EXTS

_lensfun_db   = None
_lensfun_lock = threading.Lock()

def get_lensfun_db():
    global _lensfun_db
    if _lensfun_db is None and HAS_LENSFUN:
        with _lensfun_lock:
            if _lensfun_db is None:
                _lensfun_db = lensfunpy.Database()
    return _lensfun_db


# ─── 读写 ────────────────────────────────────────────────────

def read_image(path):
    ext = Path(path).suffix.lower()
    if ext in RAF_EXTS:
        if not HAS_RAWPY:
            raise RuntimeError("读取RAF需要安装rawpy：pip install rawpy")
        with rawpy.imread(path) as raw:
            rgb = raw.postprocess(
                use_camera_wb=True,
                no_auto_bright=False,
                output_bps=8,
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                # 关键：不让rawpy自动缩放，保持原始像素
                half_size=False,
            )
        img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        # RAW转换后补偿锐化（capture sharpening）
        img = apply_capture_sharpening(img)
        return img
    try:
        pil_img = Image.open(path).convert('RGB')
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except Exception:
        pass
    try:
        with open(path, 'rb') as f:
            data = np.frombuffer(f.read(), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def apply_capture_sharpening(img_bgr, radius=0.6, amount=0.5):
    """
    RAW转换后的capture sharpening
    使用USM（非锐化掩模），轻度锐化补偿demosaic柔化
    radius=0.6像素，amount=0.5（50%），类似Lightroom默认值
    """
    img_f = img_bgr.astype(np.float32)
    # 高斯模糊
    blur_size = max(3, int(radius * 4) | 1)  # 确保是奇数
    blurred = cv2.GaussianBlur(img_f, (blur_size, blur_size), radius)
    # USM = original + amount * (original - blurred)
    sharpened = img_f + amount * (img_f - blurred)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def save_image(img, path, quality=95):
    ext = Path(path).suffix.lower()
    try:
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if ext in ['.jpg','.jpeg']:
            pil_img.save(path, 'JPEG', quality=quality)
        elif ext == '.png':
            pil_img.save(path, 'PNG')
        elif ext in ['.tif','.tiff']:
            pil_img.save(path, 'TIFF', compression='lzw')
        else:
            pil_img.save(path, 'JPEG', quality=quality)
        return True
    except Exception:
        return False


# ─── 镜头矫正 ────────────────────────────────────────────────

def apply_lens_correction(img_bgr, camera_name=None, lens_name=None,
                          focal_length=50.0, aperture=2.0,
                          correct_distortion=True, correct_ca=True,
                          correct_vignetting=True):
    if not HAS_LENSFUN:
        return img_bgr, "lensfunpy未安装"
    db = get_lensfun_db()
    cam_q  = camera_name or "Fujifilm X-T3"
    lens_q = lens_name   or "Fujifilm XF 50mm F2 R WR"
    cameras = db.find_cameras(cam_q)
    if not cameras:
        cameras = [c for c in db.find_cameras("Fujifilm")
                   if 'X-T3' in c.model or 'XT3' in c.model.replace('-','')]
    if not cameras:
        return img_bgr, f"未找到相机: {cam_q}"
    lenses = db.find_lenses(cameras[0], lens_q)
    if not lenses: lenses = db.find_lenses(cameras[0], "XF 50mm")
    if not lenses: lenses = db.find_lenses(cameras[0], "50mm")
    if not lenses:
        return img_bgr, f"未找到镜头: {lens_q}"
    camera, lens = cameras[0], lenses[0]
    h, w = img_bgr.shape[:2]
    try:
        mod = lensfunpy.Modifier(lens, camera.crop_factor, w, h)
        mod.initialize(focal_length, aperture, distance=1.0, pixel_format=np.float32)
        rgb = cv2.cvtColor(img_bgr.astype(np.float32)/255.0, cv2.COLOR_BGR2RGB)
        if correct_ca:
            coords = mod.apply_subpixel_distortion()
            if coords is not None:
                r = cv2.remap(rgb[:,:,0], coords[:,:,0,0], coords[:,:,0,1], cv2.INTER_LANCZOS4)
                g = cv2.remap(rgb[:,:,1], coords[:,:,1,0], coords[:,:,1,1], cv2.INTER_LANCZOS4)
                b = cv2.remap(rgb[:,:,2], coords[:,:,2,0], coords[:,:,2,1], cv2.INTER_LANCZOS4)
                rgb = np.stack([r,g,b], axis=2)
        if correct_distortion:
            coords = mod.apply_geometry_distortion()
            if coords is not None:
                for c in range(3):
                    rgb[:,:,c] = cv2.remap(rgb[:,:,c], coords[:,:,0], coords[:,:,1], cv2.INTER_LANCZOS4)
        if correct_vignetting:
            vig = np.ones((h,w,3), dtype=np.float32)
            mod.apply_color_modification(vig)
            rgb = np.clip(rgb*vig, 0, 1)
        result = (cv2.cvtColor(np.clip(rgb,0,1), cv2.COLOR_RGB2BGR)*255).astype(np.uint8)
        return result, f"镜头矫正✓({lens.model})"
    except Exception as e:
        return img_bgr, f"矫正出错(用原图):{e}"


def simple_ca_correction(img_bgr):
    b,g,r = cv2.split(img_bgr.astype(np.float32))
    h,w = g.shape
    def sc(ch, s):
        if abs(s-1.0)<1e-4: return ch
        M = cv2.getRotationMatrix2D((w/2,h/2),0,s)
        return cv2.warpAffine(ch,M,(w,h),flags=cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_REPLICATE)
    return cv2.merge([sc(b,0.9992), g, sc(r,1.0008)]).astype(np.uint8)


# ─── 分组 ────────────────────────────────────────────────────

def get_image_timestamp(filepath):
    try:
        img = Image.open(filepath)
        exif = img._getexif()
        if exif:
            for tag in [36867,36868,306]:
                if tag in exif:
                    try: return datetime.strptime(exif[tag],"%Y:%m:%d %H:%M:%S").timestamp()
                    except: pass
    except: pass
    return os.path.getmtime(filepath)

def extract_seq(filename):
    nums = re.findall(r'\d+', Path(filename).stem)
    return int(nums[-1]) if nums else 0

def group_images_by_sequence(image_files, group_size, progress_callback=None):
    """
    纯时间戳分组：根据拍摄间隔自动切割，不依赖文件名规律，不校验组大小。
    - 超过1张的组：做焦点堆叠
    - 恰好1张的组：直接复制原图到输出
    阈值策略：取所有相邻间隔的中位数 × 5，至少 2 秒，确保快速连拍不被切断。
    """
    if not image_files:
        return []

    if progress_callback:
        progress_callback("analyzing", "读取 EXIF 时间戳，智能分组中...")

    # 读取时间戳并按时间排序
    ts_pairs = sorted(
        [(get_image_timestamp(f), f) for f in image_files],
        key=lambda x: x[0]
    )
    timestamps = [t for t, _ in ts_pairs]
    sorted_files = [f for _, f in ts_pairs]

    if len(sorted_files) == 1:
        return [sorted_files]

    # 计算相邻间隔，动态确定切割阈值
    diffs = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    median_diff = float(np.median(diffs))
    threshold = max(median_diff * 5, 2.0)

    if progress_callback:
        progress_callback("analyzing",
            f"中位间隔 {median_diff:.2f}s，切割阈值 {threshold:.2f}s")

    # 按阈值切割分组
    raw_groups = []
    current = [sorted_files[0]]
    for i, d in enumerate(diffs):
        if d > threshold:
            raw_groups.append(current)
            current = [sorted_files[i+1]]
        else:
            current.append(sorted_files[i+1])
    raw_groups.append(current)

    # 超过 group_size 的组按 group_size 再切，防止两组被误合并
    groups = []
    for g in raw_groups:
        if len(g) > group_size:
            for i in range(0, len(g), group_size):
                chunk = g[i:i+group_size]
                if chunk:
                    groups.append(chunk)
        else:
            groups.append(g)

    singles = sum(1 for g in groups if len(g) == 1)
    stacks  = sum(1 for g in groups if len(g) > 1)
    if progress_callback:
        progress_callback("analyzing",
            f"分组完成：{stacks} 组需堆叠，{singles} 张单图直接复制")

    return groups


# ─── 关键修复：多分辨率图像对齐 ─────────────────────────────

def align_images_multiscale(images, max_align_size=1500):
    """
    多分辨率对齐：
    1. 缩小到 max_align_size 以内进行 ECC 对齐计算（快速、稳定）
    2. 把得到的位移矩阵按比例放大，应用到原始全分辨率图像
    
    解决原来 RAF 大图 ECC 不收敛导致对齐失败的问题
    """
    if len(images) <= 1:
        return images

    ref_idx = len(images) // 2
    reference = images[ref_idx]
    h_orig, w_orig = reference.shape[:2]

    # 计算缩放比例
    scale = min(max_align_size / w_orig, max_align_size / h_orig, 1.0)
    w_small = int(w_orig * scale)
    h_small = int(h_orig * scale)

    # 缩小参考图
    ref_small = cv2.resize(reference, (w_small, h_small), interpolation=cv2.INTER_AREA)
    ref_gray_small = cv2.cvtColor(ref_small, cv2.COLOR_BGR2GRAY)

    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 500, 1e-6)

    aligned = [None] * len(images)
    aligned[ref_idx] = reference.copy()

    for i, img in enumerate(images):
        if i == ref_idx:
            continue
        try:
            # 在小图上做 ECC
            img_small = cv2.resize(img, (w_small, h_small), interpolation=cv2.INTER_AREA)
            img_gray_small = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)

            warp = np.eye(2, 3, dtype=np.float32)
            _, warp = cv2.findTransformECC(
                ref_gray_small, img_gray_small,
                warp, cv2.MOTION_TRANSLATION, criteria, None, 5
            )

            # 把位移量按比例还原到原始尺寸
            if scale < 1.0:
                warp[0, 2] /= scale  # tx
                warp[1, 2] /= scale  # ty

            # 在原始全分辨率图上应用变换
            aligned[i] = cv2.warpAffine(
                img, warp, (w_orig, h_orig),
                flags=cv2.INTER_LANCZOS4 + cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_REPLICATE
            )
        except cv2.error:
            # ECC 失败时用原图（比之前版本更安全的fallback）
            aligned[i] = img.copy()

    return aligned


# ─── 关键修复：自适应 block_size ─────────────────────────────

def get_adaptive_params(h, w):
    """
    根据图像分辨率自动调整焦点堆叠参数
    JPG(压缩小图) vs RAF(2600万像素)参数差别很大
    """
    megapixels = (h * w) / 1_000_000

    if megapixels > 15:        # RAF 大图 (X-T3: 26MP)
        block_size   = 64
        smooth_radius = 25
    elif megapixels > 6:       # 中等尺寸
        block_size   = 48
        smooth_radius = 20
    else:                      # JPG 小图
        block_size   = 32
        smooth_radius = 15

    return block_size, smooth_radius


def compute_sharpness(gray_img):
    blurred = cv2.GaussianBlur(gray_img, (5,5), 0)
    return np.abs(cv2.Laplacian(blurred, cv2.CV_64F))


def focus_stack_blend(images):
    if not images:
        return None

    h, w = images[0].shape[:2]
    block_size, smooth_radius = get_adaptive_params(h, w)

    kernel = np.ones((block_size, block_size), np.float32) / block_size**2

    def calc_smooth(img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        sharp = compute_sharpness(gray).astype(np.float32)
        return cv2.filter2D(sharp, -1, kernel)

    with ThreadPoolExecutor(max_workers=min(len(images), 4)) as ex:
        smoothed = list(ex.map(calc_smooth, images))

    best_idx = np.argmax(np.stack(smoothed, axis=0), axis=0)
    result = np.zeros_like(images[0], dtype=np.float64)
    weight_sum = np.zeros((h, w), dtype=np.float64)
    ksize = smooth_radius * 2 + 1

    for i, img in enumerate(images):
        mask = cv2.GaussianBlur(
            (best_idx == i).astype(np.float32),
            (ksize, ksize), smooth_radius / 3
        )
        result += img.astype(np.float64) * mask[:,:,np.newaxis]
        weight_sum += mask

    result /= np.maximum(weight_sum[:,:,np.newaxis], 1e-8)
    return np.clip(result, 0, 255).astype(np.uint8)


# ─── 单组处理 ────────────────────────────────────────────────

def process_group(image_paths, output_path, group_num, quality=95,
                  lens_correction=True, ca_correction=True,
                  camera_name=None, lens_name=None):
    import shutil
    t0 = time.time()
    log = []

    # 单张图片：直接复制原始文件，保留原始格式和质量
    if len(image_paths) == 1:
        src = image_paths[0]
        # 输出路径保持原始扩展名
        src_ext = Path(src).suffix
        dst = Path(output_path).with_suffix(src_ext)
        try:
            shutil.copy2(src, dst)
            return True, f"单张复制原图({src_ext}) | {time.time()-t0:.1f}s"
        except Exception as e:
            return False, f"复制失败: {e}"

    # 1. 并行读取（RAF 自动做 capture sharpening）
    read_workers = min(len(image_paths), 4)

    def _read_one(path):
        try:
            img = read_image(path)
            return path, img, None
        except RuntimeError as e:
            return path, None, str(e)

    path_index = {p: i for i, p in enumerate(image_paths)}
    raw_results = [None] * len(image_paths)
    with ThreadPoolExecutor(max_workers=read_workers) as ex:
        for path, img, err in ex.map(_read_one, image_paths):
            if err:
                return False, err
            raw_results[path_index[path]] = img

    images = [img for img in raw_results if img is not None]
    del raw_results
    if not images:
        return False, "无法读取图像"

    # 2. 镜头矫正（并行处理每张）
    if lens_correction and HAS_LENSFUN:
        def _correct_one(img):
            return apply_lens_correction(
                img, camera_name=camera_name, lens_name=lens_name,
                correct_distortion=True, correct_ca=ca_correction,
                correct_vignetting=True)

        with ThreadPoolExecutor(max_workers=read_workers) as ex:
            correction_results = list(ex.map(_correct_one, images))

        images = [img for img, _ in correction_results]
        msg = correction_results[0][1] if correction_results else ""
        log.append(msg)
        del correction_results
    elif ca_correction:
        images = [simple_ca_correction(img) for img in images]
        log.append("简易CA矫正")

    # 3. 统一尺寸
    h, w = images[0].shape[:2]
    images = [cv2.resize(img,(w,h),interpolation=cv2.INTER_LANCZOS4)
              if img.shape[:2]!=(h,w) else img for img in images]

    # 4. 多分辨率对齐（修复大图对齐失败问题）
    megapixels = (h * w) / 1_000_000
    # 大图用更小的对齐尺寸，确保ECC稳定收敛
    max_align_size = 1200 if megapixels > 15 else 1500
    log.append(f"{megapixels:.0f}MP")

    try:
        aligned = align_images_multiscale(images, max_align_size=max_align_size)
        aligned = [a for a in aligned if a is not None]
        log.append("多分辨率对齐✓")
    except Exception as e:
        aligned = images
        log.append("对齐跳过")

    # 5. 焦点堆叠（自适应参数）
    result = focus_stack_blend(aligned)
    if result is None:
        return False, "融合失败"

    # 6. 保存
    if not save_image(result, output_path, quality):
        return False, f"保存失败: {output_path}"

    return True, f"{len(images)}张合成 | {' | '.join(log)} | {time.time()-t0:.1f}s"


# ─── 批量处理（多核并行）────────────────────────────────────

def process_batch(
    input_folder, output_folder,
    group_size=10, output_format="jpg", quality=95,
    lens_correction=True, ca_correction=True,
    camera_name=None, lens_name=None,
    max_workers=None,
    progress_callback=None
):
    image_files = [str(f) for f in Path(input_folder).iterdir()
                   if f.suffix.lower() in ALL_EXTS]

    if not image_files:
        return {"error":"未找到图像文件","success":0,"failed":0,
                "total_images":0,"total_groups":0,"output_files":[],"errors":[]}

    raf_count = sum(1 for f in image_files if Path(f).suffix.lower() in RAF_EXTS)
    if progress_callback:
        progress_callback("scanning",
            f"发现 {len(image_files)} 张图像（{raf_count} 张RAF）"
            + ("" if HAS_RAWPY else " ⚠️ rawpy未安装"), 5)

    os.makedirs(output_folder, exist_ok=True)

    groups = group_images_by_sequence(image_files, group_size,
        lambda s,m: progress_callback(s,m,10) if progress_callback else None)

    # 根据RAF文件大小和每组张数动态计算安全线程数
    # 56MB RAF x 解码膨胀5倍 = 每张约280MB内存，留4GB给系统和其他开销
    # 可用内存 = 32GB - 4GB = 28GB，安全线程数 = 28GB / (每组张数 x 280MB)
    if raf_count > 0:
        avg_group_size = sum(len(g) for g in groups) / max(len(groups), 1)
        mem_per_thread_gb = avg_group_size * 0.28  # 每张RAF解码后约280MB
        available_gb = 28.0
        raf_max = max(1, min(int(available_gb / mem_per_thread_gb), OPTIMAL_WORKERS))
    else:
        raf_max = OPTIMAL_WORKERS
    default_workers = raf_max
    workers = min(max_workers or default_workers, raf_max, len(groups))

    if progress_callback:
        lc = "✅lensfunpy" if HAS_LENSFUN else "⚠️简易CA"
        avg_sz = int(sum(len(g) for g in groups) / max(len(groups), 1))
        progress_callback("grouped",
            f"共 {len(groups)} 组（均{avg_sz}张/组）| {lc} | 🚀 {workers} 线程并行", 15)

    results = {
        "total_images": len(image_files), "total_groups": len(groups),
        "success": 0, "failed": 0,
        "output_files": [], "errors": [],
        "has_rawpy": HAS_RAWPY, "has_lensfun": HAS_LENSFUN,
        "workers_used": workers
    }

    lock = threading.Lock()
    completed_count = [0]

    def process_one(args):
        idx, group = args
        group_num = idx + 1
        first_name = Path(group[0]).stem
        is_single = len(group) == 1

        if is_single:
            # 单张：保留原始文件名和扩展名
            src_ext = Path(group[0]).suffix
            output_filename = f"single_{group_num:03d}_{first_name}{src_ext}"
        else:
            base_name = re.sub(r'_?\d{1,4}$', '', first_name) or first_name
            output_filename = f"stacked_{group_num:03d}_{base_name}.{output_format}"

        output_path = os.path.join(output_folder, output_filename)

        success, message = process_group(
            group, output_path, group_num, quality,
            lens_correction=lens_correction, ca_correction=ca_correction,
            camera_name=camera_name, lens_name=lens_name
        )

        with lock:
            completed_count[0] += 1
            done = completed_count[0]
            pct = 15 + int((done / len(groups)) * 80)
            if success:
                results["success"] += 1
                results["output_files"].append({
                    "group": group_num, "output": output_filename,
                    "sources": [os.path.basename(f) for f in group],
                    "message": message
                })
            else:
                results["failed"] += 1
                results["errors"].append({
                    "group": group_num, "error": message,
                    "sources": [os.path.basename(f) for f in group]
                })
            if progress_callback:
                progress_callback("processing",
                    f"已完成 {done}/{len(groups)} 组 | ✅{results['success']} ❌{results['failed']} | {workers}线程",
                    pct)
        return success, group_num

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_one,(i,g)):i for i,g in enumerate(groups)}
        for future in as_completed(futures):
            try: future.result()
            except Exception as e:
                with lock: results["failed"] += 1

    if progress_callback:
        progress_callback("done",
            f"完成！✅ {results['success']} 组成功 | ❌ {results['failed']} 组失败", 100)

    return results
