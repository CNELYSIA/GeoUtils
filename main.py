import asyncio
import cv2
import numpy as np
from osgeo import gdal
import os
from concurrent.futures import ThreadPoolExecutor
from utils.google_downloader import fetchSatelliteData
gdal.UseExceptions()

def fetchSatelliteDataReturnFileName(intZoomLevel, strRootDirectory, geojsonData, strFileName):
    asyncio.run(fetchSatelliteData(intZoomLevel, strRootDirectory, geojsonData, strFileName))
    return strFileName + ".tif"


class ImageData:
    def __init__(self, strImageName, npImageData, tupleOriginalShape, prj=None, geoTransform=None, isGdalRead=False):
        self.strImageName = strImageName
        self.npImageData = npImageData
        self.tupleOriginalShape = tupleOriginalShape
        self.prj = prj  # 投影信息
        self.geoTransform = geoTransform  # 地理变换矩阵
        self.isGdalRead = isGdalRead  # 标记图像是否通过GDAL读取


class ProcessedImageData(ImageData):
    def __init__(self, strImageName, npImageData, tupleOriginalShape, processingStep=None, prj=None,
                 geoTransform=None, isGdalRead=False):
        super().__init__(strImageName, npImageData, tupleOriginalShape, prj, geoTransform, isGdalRead)
        self.processingStep = processingStep  # 存储处理步骤的信息


class ImageManager:
    def __init__(self):
        self.dictImages = {}
        self.dictCroppedImages = {}
        self.dictStitchedImages = {}
        self.dictConvertedImages = {}
        self.dictGeoReferencedImages = {}  # 新增字典用于存储带有地理信息的图像
        self.dictAppendedImages = {}  # 新增字典用于存储追加的图像

    def appendImagesFrom(self, sourceDictName):
        if not hasattr(self, sourceDictName):
            print(f"Source dictionary '{sourceDictName}' does not exist.")
            return

        sourceDict = getattr(self, sourceDictName)
        for imgName, imgData in sourceDict.items():
            if isinstance(imgData, (ImageData, ProcessedImageData)):
                self.dictAppendedImages[imgName] = imgData
            else:
                print(f"Item {imgName} is not of type ImageData or ProcessedImageData and will be skipped.")

    # 私有排序器
    def _sortKey(self, strItem):
        try:
            return int(strItem[:3]), int(strItem[3:6]), int(strItem[6:9])
        except ValueError:
            raise ValueError(f"Invalid crop key format: {strItem}")

    # 读取图片（公共方法）
    def readImg(self, strFilePath, append=False):
        if os.path.isfile(strFilePath):
            self._addImageToDict(strFilePath, append)
        elif os.path.isdir(strFilePath):
            for strFilename in os.listdir(strFilePath):
                strFilePathFull = os.path.join(strFilePath, strFilename)
                if os.path.isfile(strFilePathFull):
                    self._addImageToDict(strFilePathFull, append)

    # 添加图片到字典（私有方法）
    def _addImageToDict(self, strPath, append=False):
        strImageName = os.path.basename(strPath).split('.')[0]
        fileExtension = strPath.lower().split('.')[-1]

        if fileExtension == 'tif' or fileExtension == 'tiff':
            dataset = gdal.Open(strPath)
            if dataset is None:
                print(f"Failed to open image: {strPath}")
                return

            npImageData = dataset.ReadAsArray()
            prj = dataset.GetProjection()
            geoTransform = dataset.GetGeoTransform()
            dataset = None  # Close the dataset
            isGdalRead = True

            # 处理NaN值，并转换为UINT8
            npImageData = np.where(np.isnan(npImageData) | np.isneginf(npImageData), 0, npImageData)  # 将NaN和-inf替换为0
            min_val = np.min(npImageData)
            max_val = np.max(npImageData)
            npImageData = ((npImageData - min_val) / (max_val - min_val) * 255).astype(np.uint8)

            if len(npImageData.shape) == 2:
                npImageData = np.expand_dims(npImageData, axis=2)
            else:
                npImageData = np.moveaxis(npImageData, 0, -1)

        else:
            npImageData = cv2.imread(strPath)
            prj = None
            geoTransform = None
            isGdalRead = False

        if npImageData is not None:
            imageData = ImageData(strImageName, npImageData, npImageData.shape[:2], prj, geoTransform, isGdalRead)
            if append:
                self.dictAppendedImages[strImageName] = imageData
            else:
                self.dictImages[strImageName] = imageData

    # 保存图片（公共方法）
    def saveImg(self, strSavePath, dictImages=None, strOutFormat='.jpg', formEE=False):
        if not os.path.exists(strSavePath):
            os.makedirs(strSavePath)

        if dictImages is None:
            dictImages = self.dictImages

        for strKey, objValue in dictImages.items():
            if isinstance(objValue, (ImageData, ProcessedImageData)):
                npImage = objValue.npImageData.copy()
                strImageName = objValue.strImageName
                prj = objValue.prj
                geoTransform = objValue.geoTransform
                isGdalRead = objValue.isGdalRead
            else:
                npImage = objValue
                strImageName = strKey
                prj = None
                geoTransform = None
                isGdalRead = False

            savePath = os.path.join(strSavePath, f"{strImageName}{strOutFormat}")

            if isGdalRead and len(npImage.shape) == 3 and npImage.shape[2] == 3:
                # 将RGB图像转换为BGR格式(通过GDAL读取的数据无法被OpenCV正常使用，颜色会有问题)
                if not formEE:
                    npImage = cv2.cvtColor(npImage, cv2.COLOR_RGB2BGR)
                else:
                    npImage = npImage


            if strOutFormat.lower() in ['.tif', '.tiff']:
                driver = gdal.GetDriverByName("GTiff")
                numBands = npImage.shape[2] if len(npImage.shape) == 3 else 1
                dataType = gdal.GDT_Byte if npImage.dtype == np.uint8 else gdal.GDT_Float32
                outDataset = driver.Create(savePath, npImage.shape[1], npImage.shape[0], numBands, dataType)
                outDataset.SetProjection(prj)
                outDataset.SetGeoTransform(geoTransform)
                if numBands == 1:
                    outBand = outDataset.GetRasterBand(1)
                    outBand.WriteArray(npImage[:, :, 0] if len(npImage.shape) == 3 else npImage)
                else:
                    for i in range(numBands):
                        outBand = outDataset.GetRasterBand(i + 1)
                        outBand.WriteArray(npImage[:, :, i])
                outDataset.FlushCache()
                outDataset = None
            else:
                cv2.imwrite(savePath, npImage)
            print(f"Saved image: {savePath}")

    # 影像裁剪（公共方法）
    def cropImg(self, intWidth=512, intHeight=512, intStep=256, intStartGroup=1):
        self.dictCroppedImages.clear()  # 清空之前的裁剪结果
        intGroup = intStartGroup

        def processImage(strImgName, objImageData):
            tupleSize = objImageData.npImageData.shape[:2]
            croppedImages = []

            intImgH = intImgW = 1
            for intStartH in range(0, tupleSize[0], intStep):
                intEndH = min(intStartH + intHeight, tupleSize[0])
                intHPad = max(0, intHeight - (tupleSize[0] - intStartH))

                for intStartW in range(0, tupleSize[1], intStep):
                    intEndW = min(intStartW + intWidth, tupleSize[1])
                    intWPad = max(0, intWidth - (tupleSize[1] - intStartW))

                    npCrop = objImageData.npImageData[intStartH:intEndH, intStartW:intEndW]

                    if intHPad > 0 or intWPad > 0:
                        npPaddedCrop = np.zeros((intHeight, intWidth, 3), dtype=np.uint8)
                        npPaddedCrop[:npCrop.shape[0], :npCrop.shape[1]] = npCrop
                        npCrop = npPaddedCrop

                    strNameImg = f"{intGroup:03d}{intImgH:03d}{intImgW:03d}"
                    croppedImages.append(
                        ProcessedImageData(strNameImg, npCrop, objImageData.tupleOriginalShape, "cropped",
                                           objImageData.prj, objImageData.geoTransform, objImageData.isGdalRead))
                    intImgW += 1

                intImgH += 1
                intImgW = 1
            return croppedImages

        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(processImage, strImgName, objImageData): strImgName for
                       strImgName, objImageData in self.dictImages.items()}
            for future in futures:
                croppedImages = future.result()
                for imgData in croppedImages:
                    self.dictCroppedImages[imgData.strImageName] = imgData

        intGroup += 1

    # 影像拼接（公共方法）
    def stitchImg(self, intWidth=512, intHeight=512, intStep=256):
        self.dictStitchedImages.clear()  # 清空之前的拼接结果

        def processImage(strImgName, objImageData):
            intOriginalHeight, intOriginalWidth = objImageData.tupleOriginalShape
            npStitchedImage = np.zeros((intOriginalHeight, intOriginalWidth, 3), dtype=np.uint8)

            listCrops = [k for k in self.dictCroppedImages.keys()]
            sortedCrops = sorted(listCrops, key=self._sortKey)

            for strCropKey in sortedCrops:
                _, intHIdx, intWIdx = self._sortKey(strCropKey)
                intHStart = (intHIdx - 1) * intStep
                intWStart = (intWIdx - 1) * intStep

                intHEnd = min(intHStart + intHeight, intOriginalHeight)
                intWEnd = min(intWStart + intWidth, intOriginalWidth)

                npCrop = self.dictCroppedImages[strCropKey].npImageData

                actualHStart = max(0, intHStart)
                actualWStart = max(0, intWStart)
                actualHEnd = min(intOriginalHeight, intHEnd)
                actualWEnd = min(intOriginalWidth, intWEnd)

                cropHStart = actualHStart - intHStart
                cropWStart = actualWStart - intWStart
                cropHEnd = cropHStart + (actualHEnd - actualHStart)
                cropWEnd = cropWStart + (actualWEnd - actualWStart)

                npStitchedImage[actualHStart:actualHEnd, actualWStart:actualWEnd] = \
                    npCrop[cropHStart:cropHEnd, cropWStart:cropWEnd]

            return ProcessedImageData(strImgName, npStitchedImage, objImageData.tupleOriginalShape, "stitched",
                                      objImageData.prj, objImageData.geoTransform, objImageData.isGdalRead)

        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(processImage, strImgName, objImageData): strImgName for
                       strImgName, objImageData in self.dictImages.items()}
            for future in futures:
                stitchedImage = future.result()
                self.dictStitchedImages[stitchedImage.strImageName] = stitchedImage

    # 图像拉伸（公共方法）
    def truncatedLinearStretch(self, dblPercentile=2):
        self.dictConvertedImages.clear()  # 清空之前的转换结果

        def convertImage(strImgName, objImageData):
            npImageData = objImageData.npImageData

            if len(npImageData.shape) == 3 and npImageData.shape[2] == 3:
                rChannel = self._percentileStretch(npImageData[:, :, 0], dblPercentile)
                gChannel = self._percentileStretch(npImageData[:, :, 1], dblPercentile)
                bChannel = self._percentileStretch(npImageData[:, :, 2], dblPercentile)
                npUint8ImageData = np.dstack((rChannel, gChannel, bChannel))
            else:
                npUint8ImageData = self._percentileStretch(npImageData, dblPercentile)
                npUint8ImageData = np.stack((npUint8ImageData,) * 3, axis=-1)

            return ProcessedImageData(strImgName, npUint8ImageData, objImageData.tupleOriginalShape, "converted",
                                      objImageData.prj, objImageData.geoTransform, objImageData.isGdalRead)

        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(convertImage, strImgName, objImageData): strImgName for
                       strImgName, objImageData in self.dictImages.items()}
            for future in futures:
                convertedImage = future.result()
                self.dictConvertedImages[convertedImage.strImageName] = convertedImage

    # 百分比拉伸（私有方法）
    def _percentileStretch(self, npImageData, dblPercentile):
        intLowerBound = np.percentile(npImageData, dblPercentile)
        intUpperBound = np.percentile(npImageData, 100 - dblPercentile)
        npClippedImageData = np.clip(npImageData, intLowerBound, intUpperBound)
        npScaledImageData = (npClippedImageData - intLowerBound) / (intUpperBound - intLowerBound) * 255
        return npScaledImageData.astype(np.uint8)

    # 赋予地理信息（公共方法）
    def assignGeoreference(self):
        if not self.dictImages:
            print("No source images found.")
            return

        srcImageName = next(iter(self.dictImages))
        srcImageData = self.dictImages[srcImageName]

        # 获取源图像的空间信息
        prj = srcImageData.prj
        geoTransform = srcImageData.geoTransform

        if prj is None or geoTransform is None:
            print("Source image does not contain spatial information.")
            return

        for targetImageName, targetImageData in self.dictAppendedImages.items():
            # 获取目标图像数据
            dstData = targetImageData.npImageData
            dstData = cv2.cvtColor(dstData, cv2.COLOR_BGR2RGB)
            # 确保目标图像尺寸与源图像相同
            imgWidth = srcImageData.tupleOriginalShape[1]
            imgHeight = srcImageData.tupleOriginalShape[0]
            dstData = cv2.resize(dstData, (imgWidth, imgHeight))

            # 创建新的带有地理信息的 GeoTIFF 文件
            newDstPath = f"{targetImageName}.tif"
            # 添加到字典
            strImageName = os.path.basename(newDstPath).split('.')[0]
            self.dictGeoReferencedImages[strImageName] = ImageData(strImageName, dstData, (imgHeight, imgWidth), prj,
                                                                 geoTransform, targetImageData.isGdalRead)




# if __name__ == "__main__":

    # str_original_path = 'test.tif'

    #可直接对某一属性进行读取
    # str_original_path = 'cropped_images'
    # obj_manager = ImageManager()
    # obj_manager.readImg(str_original_path)
    # obj_manager.dictCroppedImages = obj_manager.dictImages
    # obj_manager.stitchImg(intWidth=256, intHeight=256, intStep=256)
    # obj_manager.saveImg('./', obj_manager.dictStitchedImages, '.jpg', formEE=False)

    # # 1. 读取原始 GeoTIFF 文件
    # obj_manager.readImg(str_original_path)
    # print(f"Read images: {list(obj_manager.dictImages.keys())}")
    #
    #
    # # 2. 裁剪图像
    # obj_manager.cropImg(intWidth=256, intHeight=256, intStep=256)
    # print(f"Cropped images: {list(obj_manager.dictCroppedImages.keys())}")
    #
    # # 3. 保存裁剪后的图像
    # obj_manager.saveImg('cropped_images', obj_manager.dictCroppedImages, '.jpg',formEE=True)
    # print("Cropped images saved.")
    #
    # # 4. 拼接图像
    # obj_manager.stitchImg(intWidth=256, intHeight=256, intStep=256)
    # print(f"Stitched images: {list(obj_manager.dictStitchedImages.keys())}")
    # obj_manager.appendImagesFrom('dictStitchedImages')
    #
    # # 5. 保存拼接后的图像
    # obj_manager.saveImg('stitched_images', obj_manager.dictStitchedImages, '.jpg', formEE=True)
    # print("Stitched images saved.")
    #
    # # 6. 百分比截断线性拉伸
    # obj_manager.truncatedLinearStretch(dblPercentile=2)
    # print(f"Converted images: {list(obj_manager.dictConvertedImages.keys())}")
    #
    # # 7. 保存转换后的图像
    # obj_manager.saveImg('converted_images', obj_manager.dictConvertedImages, '.png', formEE=True)
    # print("Converted images saved.")
    #
    # # 8. 赋予地理信息
    # obj_manager.assignGeoreference()
    # print(f"Geo-referenced images: {list(obj_manager.dictGeoReferencedImages.keys())}")
    #
    # # 9. 保存带有地理信息的图像
    # obj_manager.saveImg('georeferenced_images', obj_manager.dictGeoReferencedImages, '.tif' ,formEE=True)
    # print("Geo-referenced images saved.")
    #
    #