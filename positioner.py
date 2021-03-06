import geopandas as gpd
import pandas as pd
import os
from shapely.geometry import Point
from shapefile_navigator import ShapefileNavigator
from sqlalchemy import create_engine

sh_navigator = ShapefileNavigator(working_dir='inegi2018_data_')

class ClipPoints:

    def __init__(self):
        self.ents = self.get_entidades()
        self.ents.crs = { 'init':'epsg:4326' }


    @staticmethod
    def turn_to_point_object(pair):
        longitude,latitude = pair
        p_ = Point([longitude,latitude])
        return p_


    @staticmethod
    def get_entidades():

        # Cambiar
        entidades = sh_navigator.concat_all_entities_filetype('ent')
        return entidades
        # Cambiar


    def add_point_geometry_to_df(self,df):

        if not ('lat' in df.columns and 'long' in df.columns):
            raise ValueError('Add or rename "lat" and "long" columns!')

        df_ = df.copy()

        point_objs = df_.apply(lambda x: self.turn_to_point_object((x['long'],x['lat'])),axis=1)
        df_['geometry'] = point_objs
        df_ = gpd.GeoDataFrame(df_)
        df_.crs = { 'init':'epsg:4326' }

        return df_


    def add_cve_ent(self,df):

        cols = df.columns.tolist() + ['CVE_ENT','geometry']
        df_ = self.add_point_geometry_to_df(df)
        spatially_joined_df = gpd.sjoin(df_,self.ents,op='within')[cols]

        return spatially_joined_df

    #--------------------------------------------------------------------------------
    # Te quedaste aquí: ¿Cómo puedo pegarle la clave de manzana a las coordenadas?
    #--------------------------------------------------------------------------------
    # Should the query to get the data be sorted by long and lat?
    # Should I fetch the data by batches using pandas?
    # what is the fastest approach?
    #--------------------------------------------------------------------------------
    @staticmethod
    def get_filetype(cve_ent,filetype):

        path = sh_navigator.path_to_filetypes_cve_ent(cve_ent) + filetype
        f = gpd.read_file(path).to_crs({'init': 'epsg:4326'})

        return f


if __name__ == '__main__':

    import Cred 
    cred = Cred.get('redshift_prod_creds')

    clip_points = ClipPoints()

    conn_str = f"postgres://{cred['usr']}:{cred['psw']}@{cred['host']}:{cred['port']}/{cred['db']}"
    conn = create_engine(conn_str)

    query = 'select * from clipdw_merchant.transaction_geography'
    df = pd.read_sql(query,conn)

    # Add cve_ent to DF
    df = clip_points.add_cve_ent(df)
    
    # Sort by CVE_ENT
    df.sort_values('CVE_ENT',inplace=True)
    
    # Get unique CVE_ENT
    cve_ents = df.CVE_ENT.unique()
    
    # Iterate, load file and do sjoin
    obj={}
    arr = []

    # For each cve_ent make the join (to avoid clogging the memory)
    for cve_ent in cve_ents:
        
        if cve_ent not in obj:
            obj[cve_ent] = clip_points.get_filetype(cve_ent,'m')

        ixes = df[df.CVE_ENT == cve_ent].index
        df_ = gpd.GeoDataFrame(df.loc[ixes,:])
        df_.crs = { 'init':'epsg:4326' }
        df_ = gpd.sjoin(df_,obj[cve_ent],op='within')
        arr.append(df_)

    # Concat all the joins
    joined = pd.concat(arr)
    # Get those that didn't join
    not_joined = df[~df.index.isin(joined.index)]

    a = pd.concat(list(map(lambda x:obj[x],obj.keys())))

