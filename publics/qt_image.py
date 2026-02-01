from PyQt5.QtCore import QObject, pyqtSignal, QByteArray, QBuffer, QIODevice, QSize, QRect, Qt
from PyQt5.QtGui import QImage, QPixmap, QMovie, QBrush, QPainter, QPixmapCache
import requests
from publics import request_mgr, cache_mgr, funcs, logging
from typing import Union, Tuple
import os
import enum


def add_cover_radius_angle(image: QImage,
                           width: int = -1,
                           height: int = -1,
                           cover_in_center: bool = False) -> QImage:
    resize_rate = round((width / image.width() + height / image.height()) / 2, 2)
    round_diameter_original = 7
    round_diameter_actually = int(round_diameter_original * (1 / resize_rate))

    image = image.convertToFormat(QImage.Format_ARGB32)
    if cover_in_center:
        imgsize = min(image.width(), image.height())
        width = height = min(width, height)
        rect = QRect(
            (image.width() - imgsize) / 2,
            (image.height() - imgsize) / 2,
            imgsize,
            imgsize,
        )
        image = image.copy(rect)

    # Create the output image with the same dimensions
    # and an alpha channel and make it completely transparent:
    out_img = QImage(image.size(), QImage.Format_ARGB32)
    out_img.fill(Qt.transparent)

    # Create a texture brush and paint a circle
    # with the original image onto the output image:
    brush = QBrush(image)

    # Paint the output image
    painter = QPainter(out_img)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(brush)

    # Don't draw an outline
    painter.setPen(Qt.NoPen)

    # drawing radius rect
    painter.drawRoundedRect(QRect(0, 0, image.width(), image.height()), round_diameter_actually,
                            round_diameter_actually)

    # closing painter event
    painter.end()

    if width == height == -1:
        # return original image
        return out_img
    else:
        # return scaled image
        return out_img.scaled(width, height,
                              Qt.KeepAspectRatio,
                              Qt.SmoothTransformation)


def add_round_cover(image: QImage, size=-1) -> QImage:
    # https://geek-docs.com/pyqt5/pyqt5-tutorials/g_pyqt5-how-to-create-circular-image-from-any-image.html

    image.convertToFormat(QImage.Format_ARGB32)
    # Crop image to a square:
    imgsize = min(image.width(), image.height())
    rect = QRect(
        (image.width() - imgsize) / 2,
        (image.height() - imgsize) / 2,
        imgsize,
        imgsize,
    )

    image = image.copy(rect)

    # Create the output image with the same dimensions
    # and an alpha channel and make it completely transparent:
    out_img = QImage(imgsize, imgsize, QImage.Format_ARGB32)
    out_img.fill(Qt.transparent)

    # Create a texture brush and paint a circle
    # with the original image onto the output image:
    brush = QBrush(image)

    # Paint the output image
    painter = QPainter(out_img)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(brush)

    # Don't draw an outline
    painter.setPen(Qt.NoPen)

    # drawing circle
    painter.drawEllipse(0, 0, imgsize, imgsize)

    # closing painter event
    painter.end()

    if size == -1:
        # return original image
        return out_img
    else:
        # return scaled image
        return out_img.scaled(size, size,
                              Qt.KeepAspectRatio,
                              Qt.SmoothTransformation)


def add_cover_for_pixmap(pixmap: QPixmap, size=-1) -> QPixmap:
    return QPixmap.fromImage(add_round_cover(pixmap.toImage(), size))


def add_cover_radius_angle_for_pixmap(pixmap: QPixmap,
                                      width: int = -1,
                                      height: int = -1,
                                      cover_in_center: bool = False) -> QPixmap:
    return QPixmap.fromImage(add_cover_radius_angle(pixmap.toImage(), width, height, cover_in_center))


class ImageType(enum.Enum):
    """动图图像类型"""
    Gif = enum.auto()
    Webp = enum.auto()
    OtherStatic = enum.auto()


class ImageLoadSource(enum.Enum):
    """图片加载来源"""

    HttpLink = enum.auto()  # http链接
    TiebaPortrait = enum.auto()  # 贴吧portrait
    BaiduHash = enum.auto()  # 百度hash图像
    BinaryData = enum.auto()  # 原始二进制字节串
    LocalFile = enum.auto()  # 本地文件


class ImageCoverType(enum.Enum):
    """图片蒙版类型"""

    RoundCover = enum.auto()  # 圆形蒙版
    RadiusAngleCover = enum.auto()  # 圆角蒙版
    RadiusAngleCoverCentrally = enum.auto()  # 圆角蒙版，取图片中心部分
    NoCover = enum.auto()  # 不使用蒙版


class MultipleImage(QObject):
    """图片抽象类，支持gif/webp显示与网络异步加载"""
    currentImageChanged = pyqtSignal(QImage)
    currentPixmapChanged = pyqtSignal(QPixmap)
    imageLoadFailed = pyqtSignal(str)
    imageLoadSucceed = pyqtSignal()
    __load_gif_signal = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.__load_gif_signal.connect(self.__load_gif)
        self.destroyed.connect(self.__on_destroyed)

        self.__image_source_type = None  # 图片来源类型
        self.__image_source = None  # 图片来源数据，如链接等
        self.__cover_type = None  # 蒙版类型
        self.__expect_size = (0, 0)  # 期望的大小

        self.__image_type = None  # 实际加载的图片类型，如静态图、GIF等
        self.__image_original_binary = None  # 图片原始字节串
        self.__gif_byte_array = None  # 动图字节数组 QByteArray
        self.__gif_buffer = None  # 动图数据读取器 QBuffer
        self.__gif_container = None  # 动图播放器 QMovie
        self.__static_image = None  # 静态图片 QImage
        self.__static_pixmap = None  # 静态图片 QPixmap
        self.__gif_covered_image = None  # 动图在使用圆形蒙版时已经蒙版好的 QImage

    def __on_destroyed(self):
        if self.isDynamicImage():
            self.stopPlayDynamicImage()
            self.__gif_buffer.close()
            self.__gif_byte_array.clear()

            self.__gif_buffer.deleteLater()
            self.__gif_container.deleteLater()
            del self.__gif_covered_image
        else:
            del self.__static_pixmap
            del self.__static_image

        QPixmapCache.clear()

        self.__image_type = None
        del self.__image_original_binary
        self.__image_original_binary = None
        self.__gif_byte_array = None
        self.__gif_buffer = None
        self.__gif_container = None
        self.__static_image = None
        self.__static_pixmap = None
        self.__gif_covered_image = None

    def __load_gif(self):
        def on_frame_changed():
            current_image = self.__gif_container.currentImage()
            if self.__cover_type == ImageCoverType.RoundCover:
                self.__gif_covered_image = add_round_cover(current_image)
            elif self.__cover_type in (ImageCoverType.RadiusAngleCover, ImageCoverType.RadiusAngleCoverCentrally):
                self.__gif_covered_image = add_cover_radius_angle(self.__static_image,
                                                                  cover_in_center=self.__cover_type == ImageCoverType.RadiusAngleCoverCentrally)

            self.currentImageChanged.emit(current_image)
            self.currentPixmapChanged.emit(self.currentPixmap())

        if not self.__image_original_binary:
            self.imageLoadFailed.emit(f'image binary is null')

        self.__gif_byte_array = QByteArray(self.__image_original_binary)
        self.__gif_buffer = QBuffer(self.__gif_byte_array)
        self.__gif_buffer.open(QIODevice.OpenModeFlag.ReadOnly)

        self.__gif_container = QMovie(self)

        self.__gif_container.frameChanged.connect(on_frame_changed)
        self.__gif_container.error.connect(
            lambda e: self.imageLoadFailed.emit(f'QMovie load failed because {self.__gif_container.lastErrorString()}'))

        if self.__expect_size[0] and self.__expect_size[1]:
            self.__gif_container.setScaledSize(QSize(self.__expect_size[0], self.__expect_size[1]))
        self.__gif_container.setDevice(self.__gif_buffer)
        self.__gif_container.setCacheMode(QMovie.CacheMode.CacheAll)

        if self.__gif_container.isValid():
            self.__gif_container.jumpToFrame(0)
            self.__gif_container.start()
            self.imageLoadSucceed.emit()
        else:
            self.imageLoadFailed.emit(f'QMovie is not valid')

    def __judge_image_type(self):
        if self.__image_original_binary.startswith((b'GIF87a', b'GIF89a')):
            self.__image_type = ImageType.Gif
        elif self.__image_original_binary.startswith(bytearray([52, 49, 46, 46])):
            self.__image_type = ImageType.Webp
        else:
            self.__image_type = ImageType.OtherStatic

    def __load_from_httpurl(self):
        response = requests.get(self.__image_source, headers=request_mgr.header)
        if response.status_code == 200 and response.content:
            self.__image_original_binary = response.content

            if response.headers['content-type'] == 'image/gif':
                self.__image_type = ImageType.Gif
            elif response.headers['content-type'] == 'image/webp':
                self.__image_type = ImageType.Webp
            else:
                self.__image_type = ImageType.OtherStatic
        else:
            raise Exception(f'load image {self.__image_source} failed. '
                            f'Maybe the status code was not 200, or the response body was empty.')

    def __load_from_tb_portrait(self):
        portrait_binary = cache_mgr.get_portrait(self.__image_source)
        self.__image_original_binary = portrait_binary
        self.__judge_image_type()

    def __load_from_bd_hash(self):
        image_binary = cache_mgr.get_bd_hash_img(self.__image_source)
        self.__image_original_binary = image_binary
        self.__judge_image_type()

    def __load_from_file(self):
        with open(self.__image_source, 'rb') as file:
            image_binary = file.read()

        self.__image_original_binary = image_binary
        self.__judge_image_type()

    def __load_qt_image(self):
        if not self.__image_original_binary:
            raise Exception('image binary data is null')

        if self.__image_type == ImageType.OtherStatic:
            self.__static_image = QImage()
            self.__static_image.loadFromData(self.__image_original_binary)
            self.__static_pixmap = QPixmap.fromImage(self.__static_image)

    def __resize_mask_qt_image(self):
        if self.__cover_type == ImageCoverType.RoundCover:
            if self.__expect_size[0] and self.__expect_size[1]:
                size = min(self.__expect_size[0], self.__expect_size[1])
            else:
                size = min(self.__static_image.width(), self.__static_image.height())  # 遵循原大小

            self.__static_image = add_round_cover(self.__static_image, size)
            self.__static_pixmap = QPixmap.fromImage(self.__static_image)
        elif self.__cover_type == ImageCoverType.NoCover:
            width = self.__expect_size[0] if self.__expect_size[0] else self.__static_image.width()
            height = self.__expect_size[1] if self.__expect_size[1] else self.__static_image.height()
            self.__static_image = self.__static_image.scaled(width, height,
                                                             Qt.KeepAspectRatio,
                                                             Qt.SmoothTransformation)
            self.__static_pixmap = QPixmap.fromImage(self.__static_image)
        elif self.__cover_type in (ImageCoverType.RadiusAngleCover, ImageCoverType.RadiusAngleCoverCentrally):
            width = self.__expect_size[0] if self.__expect_size[0] else self.__static_image.width()
            height = self.__expect_size[1] if self.__expect_size[1] else self.__static_image.height()

            self.__static_image = add_cover_radius_angle(self.__static_image, width, height,
                                                         cover_in_center=self.__cover_type == ImageCoverType.RadiusAngleCoverCentrally)
            self.__static_pixmap = QPixmap.fromImage(self.__static_image)
        else:
            raise Exception('cover type is invalid')

    def __load_thread(self):
        try:
            if self.__image_source_type == ImageLoadSource.HttpLink:
                self.__load_from_httpurl()
            elif self.__image_source_type == ImageLoadSource.TiebaPortrait:
                self.__load_from_tb_portrait()
            elif self.__image_source_type == ImageLoadSource.BaiduHash:
                self.__load_from_bd_hash()
            elif self.__image_source_type == ImageLoadSource.BinaryData:
                self.__image_original_binary = self.__image_source
                self.__judge_image_type()
            elif self.__image_source_type == ImageLoadSource.LocalFile:
                self.__load_from_file()
            else:
                raise TypeError('image source type is not valid')

            if self.__image_type == ImageType.OtherStatic:
                self.__load_qt_image()
                self.__resize_mask_qt_image()
                self.currentImageChanged.emit(self.__static_image)
                self.currentPixmapChanged.emit(self.__static_pixmap)
            else:
                self.__load_gif_signal.emit()
                return

        except Exception as e:
            logging.log_exception(e)
            self.imageLoadFailed.emit(str(e))
        else:
            self.imageLoadSucceed.emit()

    def isImageInfoValid(self):
        """是否有已通过 setImageInfo() 设置的图片初始信息"""
        return bool(self.__image_source)

    def isImageLoaded(self):
        """是否有已加载的图片数据"""
        if self.isImageInfoValid():
            if self.__image_type == ImageType.OtherStatic:
                return not self.__static_image.isNull()
            elif self.isDynamicImage():
                return self.__gif_container.isValid() if self.__gif_container else False
        return False

    def imageType(self) -> Union[ImageType, None]:
        """获取已加载的图像类型，在未加载时调用返回 None"""
        return self.__image_type

    def isDynamicImage(self):
        """已加载的图片是否为动图格式"""
        return self.__image_type in (ImageType.Gif, ImageType.Webp) and self.__gif_container

    def isDynamicPlaying(self):
        """动图是否在播放"""
        if self.isDynamicImage():
            return self.__gif_container.state() == QMovie.MovieState.Running
        else:
            raise Exception('image is not a dynamic image')

    def startPlayDynamicImage(self):
        """开始播放动图"""
        if self.isDynamicImage():
            self.__gif_container.start()
        else:
            raise Exception('image is not a dynamic image')

    def pausePlayDynamicImage(self):
        """暂停播放动图"""
        if self.isDynamicImage():
            self.__gif_container.setPaused(True)
        else:
            raise Exception('image is not a dynamic image')

    def unpausePlayDynamicImage(self):
        """继续播放动图"""
        if self.isDynamicImage():
            self.__gif_container.setPaused(False)
        else:
            raise Exception('image is not a dynamic image')

    def stopPlayDynamicImage(self):
        """停止播放动图"""
        if self.isDynamicImage():
            self.__gif_container.stop()
        else:
            raise Exception('image is not a dynamic image')

    def currentImage(self) -> QImage:
        """获取当前 QImage"""
        if self.__image_type == ImageType.OtherStatic:
            return self.__static_image
        elif self.isDynamicImage():
            if self.__cover_type == ImageCoverType.RoundCover:
                return self.__gif_covered_image
            else:
                return self.__gif_container.currentImage()

    def currentPixmap(self) -> QPixmap:
        """获取当前 QPixmap"""
        if self.__image_type == ImageType.OtherStatic:
            return self.__static_pixmap
        elif self.isDynamicImage():
            if self.__cover_type == ImageCoverType.RoundCover:
                return QPixmap.fromImage(self.__gif_covered_image)
            else:
                return self.__gif_container.currentPixmap()

    def destroyImage(self):
        """释放图像所占用的资源"""
        self.__on_destroyed()

    def reloadImage(self):
        """重新加载图像"""
        self.destroyImage()  # 执行内存清理
        self.loadImage()

    def loadImage(self):
        """在后台加载图像，返回加载线程对象"""
        if not self.isImageLoaded():
            return funcs.start_background_thread(self.__load_thread)

    def loadImageAndWait(self, timeout=10):
        """在后台加载图像，并在当前线程等待"""
        if not self.isImageLoaded():
            self.loadImage().join(timeout)

    def setImageInfo(self, loadFrom: ImageLoadSource,
                     sourceData: Union[str, bytes],
                     coverType: ImageCoverType = ImageCoverType.NoCover,
                     expectSize: Tuple[int, int] = (0, 0)):
        """
        设置图片信息

        Args:
            loadFrom (ImageLoadSource): 图片加载来源
            sourceData (Union[str, bytes]): 图片原始数据，如在HttpLink模式下是图片链接
            coverType (ImageCoverType): 图片蒙版类型 默认不蒙版
            expectSize (Tuple[int, int]): 期望的图片尺寸 元组传入的是期望大小的(宽度, 高度) 当两个值都为零(即默认参数)时为遵循原图片大小，不进行缩放
        """
        self.__image_source_type = loadFrom
        self.__image_source = sourceData
        self.__cover_type = coverType
        self.__expect_size = expectSize

        flag_HttpLink = (loadFrom == ImageLoadSource.HttpLink
                         and isinstance(sourceData, str)
                         and sourceData.startswith((request_mgr.SCHEME_HTTP, request_mgr.SCHEME_HTTPS)))
        flag_TbPortrait = (loadFrom == ImageLoadSource.TiebaPortrait
                           and isinstance(sourceData, str)
                           and sourceData.startswith(('tb.1.', '0')))
        flag_Bdhash = (loadFrom == ImageLoadSource.BaiduHash
                       and isinstance(sourceData, str))
        flag_bindata = (loadFrom == ImageLoadSource.BinaryData
                        and isinstance(sourceData, bytes))
        flag_localfile = (loadFrom == ImageLoadSource.LocalFile
                          and isinstance(sourceData, str)
                          and os.path.isfile(sourceData))
        flag_pool = [flag_bindata, flag_localfile, flag_Bdhash, flag_TbPortrait, flag_HttpLink]

        if True not in flag_pool:
            self.__image_source_type = None
            self.__image_source = None
            self.__cover_type = None
            self.__expect_size = None
            raise TypeError(f'sourceData \"{sourceData}\" is not compatible for source \"{loadFrom}\"')
