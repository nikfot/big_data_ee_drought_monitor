from numpy.lib.stride_tricks import sliding_window_view
import ee
import folium
import geemap.foliumap as geemap
from google.colab import drive
from google.colab import auth
import time 
import proplot as plot 
import ipygee as ui
import matplotlib.pyplot as plt
import numpy as np 
import pandas as pd 
import datetime

class DroughtResearch:
  def __init__(self,name,country,perfecture):
    self.name=name
    self.country=country
    self.perfecture=perfecture
    self.boundaries=None
    self.dates=Dates()
    self.images={}
    self.NDDI=None
    
  def get_borders(self):
    admin_borders=ee.FeatureCollection("FAO/GAUL/2015/level2")
    country_borders=admin_borders.filter(ee.Filter.eq('ADM0_NAME', self.country))
    perfecture_borders=country_borders.filter(ee.Filter.eq("ADM2_NAME", self.perfecture))
    self.boundaries=perfecture_borders
    return country_borders,perfecture_borders
  
  def set_ndvi_collection(self,name,collection):
    self.ndvi_collections[name]=collection
  
  def upload_images(self,key_name,description,scale,folder):
    for i in range(len(self.images[key_name])):
      self.upload(self.images[key_name][i],description+f"_{i+1}",scale,folder)

  def upload(self,image,description,scale,folder):
    drive.mount("/content/gdrive",force_remount=True)
    task = ee.batch.Export.image.toDrive(**{"image": image, "description": description, "scale": scale,"region": self.boundaries.geometry(), "crs": "EPSG:4326","folder": folder, 'fileFormat': 'GeoTIFF','skipEmptyTiles': True})
    task.start()
    while task.active():
      print('==> Polling for task (id: {}) Current Status: {}.'.format(task.id,task.status().get("state")))
      time.sleep(5)
      print("*** Task {} status is {}.".format(task.id,task.status().get("state")))



class Dates:
  def __init__(self):
    self.date_start=None
    self.date_end=None
  
  def set_calendar_range(self,start,end):
    self.date_start=start
    self.date_end=end
    return self


class FeatureInfo:
    def __init__(self,name,dates: Dates,boundaries,collection_type,kind):
      self.name=name
      self.dates=dates
      self.boundaries=boundaries
      self.collection=None
      self.collection_type=collection_type  
      self.kind=kind
      self.month_analogy=None

    def process_collection(self):
      self.collection = (ee.ImageCollection(self.collection_type)
                          .filterBounds(self.boundaries.geometry())
                          .filterDate(self.dates.date_start,self.dates.date_end)
                          .select(self.kind)
                          .map(lambda image: image.multiply(0.0001).copyProperties(image,['system:time_start']))
                          )
      return self

    def filter_collection_by_month(self,month)->ee.ImageCollection: 
      filtered=(self.collection
                .filterDate(self.dates.date_start,self.dates.date_end)
                .filter(ee.Filter.calendarRange(month,month,"month"))
                .select(self.kind)
                .max()
                .clip(self.boundaries))
      return filtered

    def filter_collection_by_year(self,year)->ee.ImageCollection: 
      filtered=(self.collection
                .filterDate(self.dates.date_start,self.dates.date_end)
                .filter(ee.Filter.calendarRange(year,year,"year"))
                .select(self.kind)
                .max()
                .clip(self.boundaries))
      return filtered

    def get_collection_mean(self)->ee.ImageCollection: 
      filtered=(self.collection
                .filterDate(self.dates.date_start,self.dates.date_end)
                .select(self.kind)
                .mean()
                .clip(self.boundaries))
      return filtered

    def get_monthly_feature_timeseries(self,scale)-> ui.chart.Image.series:
      chart_ts = ui.chart.Image.series(**{
            'imageCollection': self.collection.select(self.kind), 
            'region': self.boundaries,
            'reducer': ee.Reducer.mean(),
            'scale': scale
      })
      chart_ts_monthly = chart_ts.dataframe.groupby(pd.Grouper(feq="M")).mean()
      return chart_ts_monthly
      
    def get_month_analogy(self,df: pd.core.frame.DataFrame):
      newpd=df[self.kind].groupby(df.index.month).sum().reset_index()
      total_sum=newpd.sum()
      newpd[self.kind]=newpd[self.kind].div(total_sum[self.kind]).mul(100)
      newpd.rename(columns = {'index' : 'Month', f"{self.kind}" : self.kind}, inplace = True)
      self.month_analogy=newpd
      return self.month_analogy
    
    def visualize_monthly_images(self,start=1,end=12):
      visualized_collection=[]
      for i in range(start,end+1):     
        monthly_collection_viz=self.visualization(self.filter_collection_by_month(i))
        visualized_collection.append(monthly_collection_viz)
      return visualized_collection

    def visualize_yearly_images(self):
      visualized_collection=[]
      start=datetime.datetime.strptime(self.dates.date_start, "%Y-%m-%d").year
      end=datetime.datetime.strptime(self.dates.date_end, "%Y-%m-%d").year
      for i in range(start,end+1):     
        yearly_collection_viz=self.visualization(self.filter_collection_by_year(i))
        visualized_collection.append(yearly_collection_viz)
      return visualized_collection

    def get_monthly_feature_chart(self,title,subtitle,color):
      chart_ts_monthly=self.get_monthly_feature_timeseries(120)  
      self.get_month_analogy(chart_ts_monthly)
      time = chart_ts_monthly.index
      _, monthly_data = plot.subplots(suptitle=subtitle,figsize=(7, 3), tight=True)
      monthly_data.plot(time,chart_ts_monthly,label=self.kind,
              color=color, marker='o')
      monthly_data.set_xlabel("Time")
      monthly_data.set_ylabel(self.kind)
      monthly_data.format(style="seaborn",title=title)
      plot.show()
    
    def plot_bar(self,title):
      my_colors = [(x/30, 0.0,x/40 ) for x in range(len(self.month_analogy))]    
      plot=self.month_analogy.plot(x="Month",y=self.kind,color=my_colors,kind="bar",title=title,figsize=(7,4),ylim=(0,20))
      plot.set_ylabel("Contribution Percentage(%)")
      for p in plot.patches:
        if p.get_height()>0:
          plot.annotate("{:0.2f}".format(p.get_height()), (p.get_x() + p.get_width() / 2., p.get_height()), ha='center', va='center', xytext=(0, 10), textcoords='offset points')
        else:
          plot.annotate("{:0.2f}".format(p.get_height()), (p.get_x() + p.get_width() / 2., 0), ha='center', va='center', xytext=(0, 10), textcoords='offset points')

class NdviInfo(FeatureInfo):
  def __init__(self,name,dates,boundaries,collection_type):
    FeatureInfo.__init__(self,name,dates,boundaries,collection_type,"NDVI")

  def get_monthly_feature_chart(self):
    chart_ts_monthly=self.get_monthly_feature_timeseries(40)  
    self.get_month_analogy(chart_ts_monthly)
    time = chart_ts_monthly.index
    _, ndvi = plot.subplots(suptitle="Larissa's Perfecture (GR) Vegetation",figsize=(7, 3), tight=True)
    ndvi.plot(time,chart_ts_monthly,label="NDVI",
            color='forest green', marker='o')
    ndvi.set_xlabel("Time")
    ndvi.set_ylabel("NDVI")
    ndvi.set_yticks(np.arange(0.2, 0.8, 0.1))
    ndvi.format(style='seaborn',title="NDVI Statistics for period 2010-2021")
    plot.show()

  def visualization(self,image):
    viz = {'min': 0, 'max': 1, 'palette': ["#593a0e","#72601b","#818c3c","#25591f","#19270d"]}
    return image.visualize(**viz)


  def plot_bar(self):
    my_colors = [(0.0, 1-x/20, x/40) for x in range(len(self.month_analogy))]    
    plot=self.month_analogy.plot(x="Month",y="NDVI",color=my_colors,kind="bar",title='Larissa Monthly Contribution Percentage to Total NDVI',figsize=(7,4),ylim=(5,11))
    plot.set_ylabel("Contribution Percentage(%)")
    for p in plot.patches:
      plot.annotate("{:0.2f}".format(p.get_height()), (p.get_x() + p.get_width() / 2., p.get_height()), ha='center', va='center', xytext=(0, 10), textcoords='offset points')



class NdwiInfo(FeatureInfo):
  def __init__(self,name,dates,boundaries,collection_type):
    FeatureInfo.__init__(self,name,dates,boundaries,collection_type,"NDWI")
  
  def process_collection(self):
      self.collection = (ee.ImageCollection(self.collection_type)
                          .filterBounds(self.boundaries.geometry())
                          .filterDate(self.dates.date_start,self.dates.date_end)
                          .map(lambda image: image.multiply(0.0001).addBands(image.normalizedDifference(["sur_refl_b02","sur_refl_b07"]).rename('NDWI')).copyProperties(image,['system:time_start']))
                          .select(self.kind)
                        )
      return self

  def get_monthly_feature_chart(self):
    chart_ts_monthly=self.get_monthly_feature_timeseries(120)  
    self.get_month_analogy(chart_ts_monthly)
    time = chart_ts_monthly.index
    _, ndwi = plot.subplots(suptitle="Larissa's Perfecture (GR) Water Index",figsize=(7, 3), tight=True)
    ndwi.plot(time,chart_ts_monthly,label="NDWI",
            color='aqua', marker='o')
    ndwi.set_xlabel("Time")
    ndwi.set_ylabel("NDWI")
    ndwi.format(style='seaborn',title="NDWI Statistics for period 2010-2021")
    plot.show()

  def visualization(self,image):
    viz = {'min': 0, 'max': 1, 'palette': ["#593a0e","#72601b","#818c3c","#25591f","#19270d"]}
    return image.visualize(**viz)


  def plot_bar(self):
    my_colors = [(0.0, x/30, 1-x/20) for x in range(len(self.month_analogy))]    
    plot=self.month_analogy.plot(x="Month",y="NDWI",color=my_colors,kind="bar",title='Larissa Monthly Contribution Percentage to Total NDWI',figsize=(7,4),ylim=(0,13))
    plot.set_ylabel("Contribution Percentage(%)")
    for p in plot.patches:
      if p.get_height()>0:
        plot.annotate("{:0.2f}".format(p.get_height()), (p.get_x() + p.get_width() / 2., p.get_height()), ha='center', va='center', xytext=(0, 10), textcoords='offset points')
      else:
        plot.annotate("{:0.2f}".format(p.get_height()), (p.get_x() + p.get_width() / 2., 0), ha='center', va='center', xytext=(0, 10), textcoords='offset points')

  def get_monthly_feature_timeseries(self,scale)-> ui.chart.Image.series:
     chart_ts = ui.chart.Image.series(**{
           'imageCollection': self.collection, 
           'region': self.boundaries,
           'reducer': ee.Reducer.mean(),
           'scale': scale
     })
     chart_ts_monthly = chart_ts.dataframe.groupby(pd.Grouper(freq="M")).mean()
     return chart_ts_monthly

class NddiInfo(FeatureInfo):
  def __init__(self,name,dates,boundaries,collection_type):
    FeatureInfo.__init__(self,name,dates,boundaries,collection_type,"NDDI")

  def process_collection(self,ndvi: ee.ImageCollection,ndwi: ee.ImageCollection):
    self.collection = (ee.ImageCollection.combine(ndvi,ndwi)
                        .map(lambda image: image.multiply(0.0001).addBands(image.normalizedDifference(["NDVI","NDWI"]).rename('NDDI')).copyProperties(image,['system:time_start']))
                        .select(self.kind)
                      )
    return self

  def get_monthly_feature_chart(self):
    chart_ts_monthly=self.get_monthly_feature_timeseries(120)  
    self.get_month_analogy(chart_ts_monthly)
    time = chart_ts_monthly.index
    _, ndwi = plot.subplots(suptitle="Larissa's Perfecture (GR) Drought Index",figsize=(7, 3), tight=True)
    ndwi.plot(time,chart_ts_monthly,label="NDDI",
            color='terracotta', marker='o')
    ndwi.set_xlabel("Time")
    ndwi.set_ylabel("NDDI")
    ndwi.format(style='seaborn',title="NDDI Statistics for period 2010-2021")
    plot.show()

  def visualization(self,image):
    viz = {'min': 0.0, 'max': 0.7, 'palette': ["#1D47D2","#11C9D8","#559E54","#CCA202","#9C0000"]}
    #viz = {'min': 0, 'max': 1, 'palette': ["#224B0C","#42855B","#C1D5A4","#AC4425","#F0F2B6"]}
    return image.visualize(**viz)


  def plot_bar(self):
    my_colors = [(1-x/30, x/40,0.0 ) for x in range(len(self.month_analogy))]    
    plot=self.month_analogy.plot(x="Month",y="NDDI",color=my_colors,kind="bar",title='Larissa Monthly Contribution Percentage to Total NDDI',figsize=(7,4),ylim=(0,12))
    plot.set_ylabel("Contribution Percentage(%)")
    for p in plot.patches:
      if p.get_height()>0:
        plot.annotate("{:0.2f}".format(p.get_height()), (p.get_x() + p.get_width() / 2., p.get_height()), ha='center', va='center', xytext=(0, 10), textcoords='offset points')
      else:
        plot.annotate("{:0.2f}".format(p.get_height()), (p.get_x() + p.get_width() / 2., 0), ha='center', va='center', xytext=(0, 10), textcoords='offset points')

class NdsiInfo(FeatureInfo):
  def __init__(self,name,dates,boundaries,collection_type):
    FeatureInfo.__init__(self,name,dates,boundaries,collection_type,"NDSI")

class VciInfo(FeatureInfo):
  def __init__(self,name,dates,boundaries,collection_type):
    FeatureInfo.__init__(self,name,dates,boundaries,collection_type,"VCI")
#VCI = 100 * (NDVI - NDVI min) / (NDVI max - NDVI min) (Kogan, 1990)
  def process_collection(self,ndvi):
    min_ndvi=ndvi.collection.select(ndvi.kind).min()
    max_ndvi=ndvi.collection.select(ndvi.kind).max()
    self.collection = (ndvi.collection
                        .filterBounds(self.boundaries.geometry())
                        .filterDate(self.dates.date_start,self.dates.date_end)
                        .select(ndvi.kind)
                        .map(lambda image: image
                             .multiply(0.0001)
                             .select(ndvi.kind)
                             .addBands(
                                 image.select(ndvi.kind)
                                      .subtract(min_ndvi)
                                      .divide(max_ndvi.subtract(min_ndvi)
                                                )
                                      .multiply(100).rename(self.kind)
                                      )
                             .copyProperties(image,['system:time_start']))
                        .select(self.kind)
                      )
    return self

class LstInfo(FeatureInfo):
  def __init__(self,name,dates,boundaries,collection_type):
     FeatureInfo.__init__(self,name,dates,boundaries,collection_type,"LST_Day_1km")

  def process_collection(self):
     self.collection = (ee.ImageCollection(self.collection_type)
                         .filterBounds(self.boundaries.geometry())
                         .filterDate(self.dates.date_start,self.dates.date_end)
                         .select(self.kind)
                         .map(lambda image: image.multiply(0.02).copyProperties(image,['system:time_start']))
                         )
     return self

class TciInfo(FeatureInfo):
  def __init__(self,name,dates,boundaries,collection_type):
     FeatureInfo.__init__(self,name,dates,boundaries,collection_type,"TCI")

  def process_collection(self,featureInfo):
      min_featureInfo=featureInfo.collection.select(featureInfo.kind).min()
      max_featureInfo=featureInfo.collection.select(featureInfo.kind).max()
      divisionInfo=min_featureInfo.subtract(max_featureInfo)
      self.collection = (featureInfo.collection
                          .filterBounds(self.boundaries.geometry())
                          .filterDate(self.dates.date_start,self.dates.date_end)
                          .select(featureInfo.kind)
                          .map(lambda image: image
                               .select(featureInfo.kind)
                               .addBands(
                                   image.select(featureInfo.kind)
                                        .multiply(-1)
                                        .add(min_featureInfo)
                                        .divide(divisionInfo
                                                  )
                                        .multiply(100).rename(self.kind)
                                        )
                               .copyProperties(image,['system:time_start']))
                          .select(self.kind)
                        )
      return self

class VhiInfo(FeatureInfo):
  def __init__(self,name,dates,boundaries,collection_type,weight=0.5):
     FeatureInfo.__init__(self,name,dates,boundaries,collection_type,"VHI")
     self.weight=0.5
  def process_collection(self,vci,tci):
     self.collection = (ee.ImageCollection.combine(vci.collection,tci.collection)
                         .filterBounds(self.boundaries.geometry())
                         .select(vci.kind,tci.kind)
                         .filterDate(self.dates.date_start,self.dates.date_end)
                         .map(lambda image: image
                              .multiply(0.0001)                            
                              .addBands(image.select(vci.kind)
                                             .multiply(self.weight)
                                             .add(image.select(tci.kind)
                                                       .multiply(1-self.weight)
                                             )
                                             .rename(self.kind)
                              )
                              .copyProperties(image,['system:time_start']))
                         .select(self.kind)
                       )
     return self
  def visualization(self,image):
    viz = {'min': 10, 'max': 70, 'palette': ["#9C0000","#CCA202","#559E54","#11C9D8","#1D47D2"]}
    #viz = {'min': 0, 'max': 1, 'palette': ["#224B0C","#42855B","#C1D5A4","#AC4425","#F0F2B6"]}
    return image.visualize(**viz)

class NmdiInfo(FeatureInfo):
  def __init__(self,name,dates,boundaries,collection_type):
     FeatureInfo.__init__(self,name,dates,boundaries,collection_type,"NMDI")
  def process_collection(self):
     self.collection = (ee.ImageCollection(self.collection_type)
                          .filterBounds(self.boundaries.geometry())
                          .select("sur_refl_b02","sur_refl_b06", "sur_refl_b07")
                          .filterDate(self.dates.date_start,self.dates.date_end)
                          .map(lambda image: image.multiply(0.0001)
                                                  .addBands(image.select("sur_refl_b02")
                                                                 .subtract(image.select("sur_refl_b06"))
                                                                 .add(image.select("sur_refl_b07"))
                                                                 .divide(
                                                                     image.select("sur_refl_b02")
                                                                          .add(image.select("sur_refl_b06"))
                                                                          .subtract(image.select("sur_refl_b07"))
                                                                 )
                                                                 .rename(self.kind))
                                                  .copyProperties(image,['system:time_start']))
                          .select(self.kind)
                        )
     return self

  def visualization(self,image):
    viz = {'min': 0.3, 'max': 0.7, 'palette': ["#1D47D2","#11C9D8","#559E54","#CCA202","#9C0000"]}
    #viz = {'min': 0, 'max': 1, 'palette': ["#224B0C","#42855B","#C1D5A4","#AC4425","#F0F2B6"]}
    return image.visualize(**viz)

################## AUTH ####################################
try:
  ee.Initialize()
except Exception as e:
  ee.Authenticate()
  ee.Initialize()

##################### INITIALIZE RESEARCH ###############################
study = DroughtResearch("LARISSA_DROUGHT_2010_2021","Greece","Larisis")
study.dates.set_calendar_range("2010-01-01","2021-12-31")
country,perfecture=study.get_borders()
######################################################################
#################### GET NDVI INFO & CHARTS ##########################
ndvi=NdviInfo("MODIS_NDVI",study.dates,study.boundaries,"MODIS/006/MOD13A2").process_collection()
study.images["NDVI"]=ndvi.visualize_monthly_images()
ndvi.get_monthly_feature_chart()
ndvi.plot_bar()

######################## UPLOAD IMAGES #################################
description=study.name + " "+feature_ndvi.name
study.upload_images(feature_ndvi.kind,description,40,"larissa_drought_2021")

########################################################################
#################### GET NDWI INFO & CHARTS ##############################
ndwi=NdwiInfo("MODIS_NDWI",study.dates,study.boundaries,"MODIS/061/MOD09A1").process_collection()
study.images["NDWI"]=ndwi.visualize_monthly_images()
ndwi.get_monthly_feature_chart()
ndwi.plot_bar()

######################## UPLOAD IMAGES #################################
description=study.name + " "+feature_ndwi.name
study.upload_images(feature_ndwi.kind,description,40,"larissa_drought_2021")

########################################################################
#################### GET NDDI INFO & CHARTS ##############################
nddi=NddiInfo("MODIS_NDDI",study.dates,study.boundaries,"").process_collection(ndvi.collection,ndwi.collection)
study.images["NDDI"]=nddi.visualize_monthly_images(start=5)
study.images["NDDI_yearly"]=nddi.visualize_yearly_images()
nddi.get_monthly_feature_chart()
nddi.plot_bar()

######################## UPLOAD IMAGES #################################
description=study.name + " "+ nddi.name
study.upload_images(nddi.kind,description,40,"larissa_drought_2021")
study.upload_images(nddi.kind+"_yearly",description+"_yearly",40,"larissa_drought_2021")

########################################################################
#################### GET NDSI INFO & CHARTS ##############################
ndsi=NdsiInfo("MODIS_NDSI",study.dates,study.boundaries,"MODIS/MOD09GA_006_NDSI").process_collection()
ndsi.get_monthly_feature_chart("NDSI Statistics for period 2010-2021","Larissa's Perfecture (GR) Ice Index","azure")
ndsi.plot_bar("Larissa Monthly Contribution Percentage to Total NDSI")

# #######################################################################
# ################### GET VCI INFO & CHARTS ##############################
vci=VciInfo("MODIS_VCI",study.dates,study.boundaries,"").process_collection(ndvi)
vci.get_monthly_feature_chart("VCI Statistics for period 2010-2021","Larissa's Perfecture (GR) Vegetation Condition Index","moss")
vci.plot_bar("Larissa Monthly Contribution Percentage to Total VCI")

# ########################################################################
# #################### GET LST INFO & CHARTS ##############################
lst=LstInfo("MODIS_LST",study.dates,study.boundaries,"MODIS/061/MOD11A1").process_collection()
lst.get_monthly_feature_chart("LST Statistics for period 2010-2021","Larissa's Perfecture (GR) Land Surface Temperature","salmon")
lst.plot_bar("Larissa Monthly Contribution Percentage to Total LST")

# ########################################################################
# #################### GET TCI INFO & CHARTS ##############################
tci=TciInfo("MODIS_TCI",study.dates,study.boundaries,"").process_collection(lst)
tci.get_monthly_feature_chart("TCI Statistics for period 2010-2021","Larissa's Perfecture (GR) Temperature Condition Index","dust rose")
tci.plot_bar("Larissa Monthly Contribution Percentage to Total TCI")

########################################################################
#################### GET NMDI INFO & CHARTS ##############################
nmdi=NmdiInfo("MODIS_NMDI",study.dates,study.boundaries,"MODIS/061/MOD09A1").process_collection()
nmdi.get_monthly_feature_chart("NMDI Statistics for period 2010-2021","Larissa's Perfecture (GR) Normalized Multi-Band Index","dust rose")
nmdi.plot_bar("Larissa Monthly Contribution Percentage to Total NMDI")

######################## UPLOAD IMAGES #################################
description=study.name + " "+ nmdi.name
study.images["NMDI"]=nmdi.visualize_monthly_images()
study.images["NMDI_yearly"]=nmdi.visualize_yearly_images()
study.upload_images(nmdi.kind,description,40,"larissa_drought_2021")
study.upload_images(nmdi.kind+"_yearly",description+"_yearly",40,"larissa_drought_2021")

########################################################################
#################### GET VHI INFO & CHARTS ##############################
vhi=VhiInfo("MODIS_VHI",study.dates,study.boundaries,"").process_collection(vci,tci)
vhi.get_monthly_feature_chart("VHI Statistics for period 2010-2021","Larissa's Perfecture (GR) Vegetation Health Index","dust rose")
vhi.plot_bar("Larissa Monthly Contribution Percentage to Total VHI")

######################## UPLOAD IMAGES #################################
description=study.name + " "+ vhi.name
study.images["VHI"]=vhi.visualize_monthly_images(4,12)
study.images["VHI_yearly"]=vhi.visualize_yearly_images()
study.upload_images(vhi.kind,description,40,"larissa_drought_2021")
study.upload_images(vhi.kind+"_yearly",description+"_yearly",40,"larissa_drought_2021")


###################### BOUNDARY MAP ##################################
Map = geemap.Map(center=[39,22], zoom=7)
Map.addLayer(country,{'color': 'blue'}, name= study.country)
Map.addLayer(perfecture,{'color': 'red'}, name= study.perfecture)
Map.addLayer(vhi.visualization(vhi.get_collection_mean()))
Map
