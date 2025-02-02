import os
import glob
from osgeo import gdal
import math
import asyncio
import aiohttp

strUserAgents = [
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.101 Safari/537.36',
    'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US) AppleWebKit/532.5 (KHTML, like Gecko) Chrome/4.0.249.0 Safari/532.5',
    'Mozilla/5.0 (Windows; U; Windows NT 5.2; en-US) AppleWebKit/532.9 (KHTML, like Gecko) Chrome/5.0.310.0 Safari/532.9',
    'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/534.7 (KHTML, like Gecko) Chrome/7.0.514.0 Safari/534.7',
    'Mozilla/5.0 (Windows; U; Windows NT 6.0; en-US) AppleWebKit/534.14 (KHTML, like Gecko) Chrome/9.0.601.0 Safari/534.14',
    'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US) AppleWebKit/534.14 (KHTML, like Gecko) Chrome/10.0.601.0 Safari/534.14',
    'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US) AppleWebKit/534.20 (KHTML, like Gecko) Chrome/11.0.672.2 Safari/534.20',
    'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/534.27 (KHTML, like Gecko) Chrome/12.0.712.0 Safari/534.27',
    'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/535.1 (KHTML, like Gecko) Chrome/13.0.782.24 Safari/535.1'
]


def convertLatDegToTileNum(latDeg, lonDeg, zoomLevel):
    latRad = math.radians(latDeg)
    n = 2.0 ** zoomLevel
    xTile = int((lonDeg + 180.0) / 360.0 * n)
    yTile = int((1.0 - math.log(math.tan(latRad) + (1 / math.cos(latRad))) / math.pi) / 2.0 * n)
    return (xTile, yTile)


def convertRightLatDegToTileNum(latDeg, lonDeg, zoomLevel):
    latRad = math.radians(latDeg)
    n = 2.0 ** zoomLevel
    xTile = int((lonDeg + 180.0) / 360.0 * n) + 1
    yTile = int((1.0 - math.log(math.tan(latRad) + (1 / math.cos(latRad))) / math.pi) / 2.0 * n) + 1
    return (xTile, yTile)


def calculateLonEdgesFromX(xTile, zoomLevel):
    tileCount = pow(2, zoomLevel)
    unit = 360 / tileCount
    lon1 = -180 + xTile * unit
    lon2 = lon1 + unit
    return (lon1, lon2)


def calculateLatEdgesFromY(yTile, zoomLevel):
    tileCount = pow(2, zoomLevel)
    unit = 1 / tileCount
    relativeY1 = yTile * unit
    relativeY2 = relativeY1 + unit
    lat1 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * relativeY1))))
    lat2 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * relativeY2))))
    return (lat1, lat2)


def getTileEdges(xTile, yTile, zoomLevel):
    lat1, lat2 = calculateLatEdgesFromY(yTile, zoomLevel)
    lon1, lon2 = calculateLonEdgesFromX(xTile, zoomLevel)
    return [lon1, lat1, lon2, lat2]


def georeferenceRasterTile(xTile, yTile, zoomLevel, filePath):
    bounds = getTileEdges(xTile, yTile, zoomLevel)
    fileName, fileExtension = os.path.splitext(filePath)
    gdal.Translate(fileName + '.tif', filePath, outputSRS='EPSG:4326', outputBounds=bounds)


async def downloadTile(session, xTile, yTile, zoomLevel, rootDirectory):
    strTilePath = f"https://mt2.google.com/vt/lyrs=s@157&hl=en&gl=us&src=app&x={xTile}&y={yTile}&z={zoomLevel}"
    strFilePath = os.path.join(rootDirectory, str(zoomLevel), str(xTile), f"{yTile}.png")
    if not os.path.isfile(strFilePath):
        try:
            async with session.get(strTilePath) as response:
                if response.status == 200:
                    os.makedirs(os.path.dirname(strFilePath), exist_ok=True)
                    with open(strFilePath, 'wb') as f:
                        while True:
                            chunk = await response.content.read(1024)
                            if not chunk:
                                break
                            f.write(chunk)
                    print(f"Tile {xTile}_{yTile} downloaded successfully.")
                    georeferenceRasterTile(xTile, yTile, zoomLevel, strFilePath)
                else:
                    print(f"Warning: Tile {xTile}_{yTile} request failed with status code {response.status}")
        except Exception as e:
            print(f"Failed to download Tile {xTile}_{yTile}: {e}")


def mergeTiles(inputPattern, outputPath):
    strVrtPath = "tiles.vrt"
    gdal.BuildVRT(strVrtPath, sorted(glob.glob(inputPattern)))
    gdal.Translate(outputPath, strVrtPath)


async def fetchSatelliteData(intZoomLevel, strRootDirectory, geojsonData, strFileName):
    def readGeoJson(data):
        lstCoordinates = data['features'][0]['geometry']['coordinates'][0]  # Assuming the first Feature's first polygon

        dblMinLon, dblMaxLon = float('inf'), -float('inf')
        dblMinLat, dblMaxLat = float('inf'), -float('inf')

        for lon, lat in lstCoordinates:
            dblMinLon = min(dblMinLon, lon)
            dblMaxLon = max(dblMaxLon, lon)
            dblMinLat = min(dblMinLat, lat)
            dblMaxLat = max(dblMaxLat, lat)

        return {
            'LT_lat': dblMaxLat, 'LT_lon': dblMinLon,  # Left Top corner
            'RB_lat': dblMinLat, 'RB_lon': dblMaxLon   # Right Bottom corner
        }

    dctCoords = readGeoJson(geojsonData)
    dblLtLat = dctCoords['LT_lat']
    dblLtLon = dctCoords['LT_lon']
    dblRbLat = dctCoords['RB_lat']
    dblRbLon = dctCoords['RB_lon']

    tplLeftTop = convertLatDegToTileNum(dblLtLat, dblLtLon, intZoomLevel)
    tplRightBottom = convertRightLatDegToTileNum(dblRbLat, dblRbLon, intZoomLevel)

    lstTasks = [(x, y) for x in range(tplLeftTop[0], tplRightBottom[0]) for y in range(tplLeftTop[1], tplRightBottom[1])]

    objConnector = aiohttp.TCPConnector(limit=100)
    async with aiohttp.ClientSession(connector=objConnector, proxy="http://127.0.0.1:7890") as session:
        await asyncio.gather(*[downloadTile(session, x, y, intZoomLevel, strRootDirectory) for x, y in lstTasks])

    strFileName = strFileName + ".tif"

    print("Starting to merge tiles...")
    strInputPattern = os.path.join(strRootDirectory, str(intZoomLevel), "*", "*.tif")
    mergeTiles(strInputPattern, os.path.join(strRootDirectory, strFileName))
    print("Tile merging completed.")


# if __name__ == "__main__":
#     intZoomLevel = 20
#     strRootDirectory = "D:\\satellite\\"
#     geojsonData = {
#     "type": "FeatureCollection",
#     "features": [
#         {
#             "type": "Feature",
#             "geometry": {
#                 "type": "Polygon",
#                 "coordinates": [
#                     [
#                         [
#                             117.17154908652023,
#                             36.671714860327796
#                         ],
#                         [
#                             117.18618892704451,
#                             36.671714860327796
#                         ],
#                         [
#                             117.18618892704451,
#                             36.68782363615106
#                         ],
#                         [
#                             117.17154908652023,
#                             36.68782363615106
#                         ],
#                         [
#                             117.17154908652023,
#                             36.671714860327796
#                         ]
#                     ]
#                 ]
#             }
#         }
#     ]
# }
#     strFileName = "satellite_data"
#     asyncio.run(fetchSatelliteData(intZoomLevel, strRootDirectory, geojsonData, strFileName))




