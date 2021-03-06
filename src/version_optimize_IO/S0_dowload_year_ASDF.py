
## download modules
import time
import obspy
import pyasdf
import os, glob
import numpy as np
import noise_module
import pandas as pd
from obspy import UTCDateTime
from obspy.clients.fdsn import Client

'''
This script downloads data from IRIS-DMC for Cascadia, cleans up the traces, 
and save the data into ASDF data format.

author: Marine Denolle (mdenolle@fas.harvard.edu) - 11/16/18

modified by Chengxin Jiang on Feb.18.2019 to make it flexiable for downloading 
data in a range of days instead of a whole year. add a subfunction to output 
the station list to a CSV file and indicate the provenance of the downloaded 
ASDF files. (Feb.22.2019)

allow to download the data based on an existing file of station list

A beginning of nice NoisePy journey! 
'''

direc  = "/Users/chengxin/Documents/Harvard/Kanto_basin/code/KANTO/data_download"
dlist  = os.path.join(direc,'station.lst')

#----check whether folder exists------
if not os.path.isdir(direc):
    os.mkdir(direc)

## download parameters
client = Client('IRIS')                         # client
NewFreq = 10                                    # resampling at X samples per seconds 
down_all = True                                 # download all stations according to a panda table

#-----parameters for 
checkt   = True                                  # check for traces with points bewtween sample intervals
resp     = False                                 # boolean to remove instrumental response
resp_dir = 'none'
pre_filt = [0.04,0.05,4,5]
oput_CSV = True                                 # output station.list to a CSV file to be used in later stacking steps
flag     = True                                 # print progress when running the script
inc_days   = 5                                  # number of days for each request

#---provence of the data in ASDF files--
if resp and checkt:
    tags = 'time_resp'
elif checkt:
    tags = 'time_checked'
elif resp:
    tags = 'resp_removed'
else:
    tags = 'raw-recordings'

#-----download one by one and input manually------
if not down_all:

    lamin,lomin,lamax,lomax=46.9,-123,48.8,-121.1   # regional box: min lat, min lon, max lat, max lon
    chan= 'HH*'                                      # channel
    net = "UW"                                        # network
    sta = "STOR"                                      # station
    start_date = '2016_05_01'
    end_date   = '2016_05_05'

    #-------initialize time information------
    starttime = obspy.UTCDateTime(int(start_date[:4]),int(start_date[5:7]),int(start_date[8:]))       
    endtime   = obspy.UTCDateTime(int(end_date[:4]),int(end_date[5:7]),int(end_date[8:]))

    #-----in case there are no data here------
    try:
        inv = client.get_stations(network=net, station=sta, channel=chan, location='*', \
            starttime = starttime, endtime=endtime,minlatitude=lamin, maxlatitude=lamax, \
            minlongitude=lomin, maxlongitude=lomax)
    except Exception as e:
        print('Abort! '+type(e))
        exit()

    if flag:
        print(inv)

    # loop through networks
    for K in inv:
        # loop through stations
        for sta in K:
            net_sta = K.code + "." + sta.code

            # write all channels into one ASDF file
            f1 = direc + "/" + str(K.code) + "."  + str(sta.code) + ".h5"
            
            if os.path.isfile(f1):
                raise IOError('file %s already exists!' % f1)
            
            with pyasdf.ASDFDataSet(f1,compression="gzip-3") as ds:

                #------add the inventory for all components + all time of this tation-------
                sta_inv = client.get_stations(network=net,station=sta,channel=chan,starttime = starttime, endtime=endtime,level="response")
                ds.add_stationxml(sta_inv)

                # loop through channels
                for chan in sta:

                    #----get a list of all days within the targeted period range----
                    all_days = noise_module.get_event_list(start_date,end_date,inc_days)

                    #---------loop through the days--------
                    for ii in range(len(all_days)-1):
                        day1  = all_days[ii]
                        day2  = all_days[ii+1]
                        year1 = int(day1[:4])
                        year2 = int(day2[:4])
                        mon1  = int(day1[5:7])
                        mon2  = int(day2[5:7])
                        iday1 = int(day1[8:]) 
                        iday2 = int(day2[8:])

                        t1=obspy.UTCDateTime(year1,mon1,iday1)
                        t2=obspy.UTCDateTime(year2,mon2,iday2)
                                
                        # sanity checks
                        if flag:
                            print(K.code + "." + sta.code + "." + chan.code+' at '+str(t1)+'.'+str(t2))
                        
                        try:
                            # get data
                            t0=time.time()
                            tr = client.get_waveforms(network=K.code, station=sta.code, channel=chan.code, location='*', \
                                starttime = t1, endtime=t2)
                            t1=time.time()

                        except Exception as e:
                            print(e)
                            continue
                            
                        if len(tr):
                            # clean up data
                            t2=time.time()
                            tr = noise_module.preprocess_raw(tr,sta_inv,NewFreq,checkt,pre_filt,resp,resp_dir)
                            t3=time.time()

                            # only keep the one with good data after processing
                            if len(tr)>0:
                                if len(tr)==1:
                                    new_tags = tags+'_{0:04d}_{1:02d}_{2:02d}_{3}'.format(tr[0].stats.starttime.year,\
                                        tr[0].stats.starttime.month,tr[0].stats.starttime.day,chan.code.lower())
                                    ds.add_waveforms(tr,tag=new_tags)
                                else:
                                    for ii in range(len(tr)):
                                        new_tags = tags+'_{0:04d}_{1:02d}_{2:02d}_{3}'.format(tr[ii].stats.starttime.year,\
                                            tr[ii].stats.starttime.month,tr[ii].stats.starttime.day,chan.code.lower())
                                        ds.add_waveforms(tr[ii],tag=new_tags)

                            if flag:
                                print(ds) # sanity check
                                print('downloading data %6.2f s; pre-process %6.2f s' % ((t1-t0),(t3-t2)))

                #------add the inventory for all components + all time of this tation-------
                sta_inv = client.get_stations(network=net, station=sta,level="response")
                ds.add_stationxml(sta_inv)

#----it gets much faster with a station lst
else:
    if not os.path.isfile(dlist):
        raise IOError('file %s not exist! double check!' % dlist)

    #----read station info------
    locs = pd.read_csv(dlist)
    nsta = len(locs)

    #----loop through each station----
    for ii in range(nsta):
        chan = locs.iloc[ii]['channel']
        net  = locs.iloc[ii]['network']
        sta  = locs.iloc[ii]['station']
        lat  = locs.iloc[ii]['latitude']
        lon  = locs.iloc[ii]['longitude']
        start_date = locs.iloc[ii]['start_date']
        end_date   = locs.iloc[ii]['end_date']

        #----the region to ensure station is unique-----
        latmin = lat-0.2
        latmax = lat+0.2
        lonmin = lon-0.2
        lonmax = lon+0.2

        #-------initialize time information------
        starttime=obspy.UTCDateTime(int(start_date[:4]),int(start_date[5:7]),int(start_date[8:]))       
        endtime=obspy.UTCDateTime(int(end_date[:4]),int(end_date[5:7]),int(end_date[8:]))

        #-----in case there are no data here------
        try:
            inv = client.get_stations(network=net, station=sta, channel=chan, location='*', \
                starttime = starttime, endtime=endtime,minlatitude=lamin, maxlatitude=lamax, \
                minlongitude=lomin, maxlongitude=lomax)
        except Exception as e:
            print('no information for %s due to %s' % (sta,e))

        if flag:
            print(inv)

        if oput_CSV:
            noise_module.make_stationlist_CSV(inv,direc)

        # loop through networks
        for K in inv:
            # loop through stations
            for sta in K:
                net_sta = K.code + "." + sta.code

                # write all channels into one ASDF file
                f1 = direc + "/" + str(K.code) + "."  + str(sta.code) + ".h5"
                
                if os.path.isfile(f1):
                    raise IOError('file %s already exists!' % f1)
                
                with pyasdf.ASDFDataSet(f1,compression="gzip-3") as ds:

                    #------add the inventory for all components + all time of this tation-------
                    sta_inv = client.get_stations(network=net, station=sta,level="response")
                    ds.add_stationxml(sta_inv)

                    # loop through channels
                    for chan in sta:

                        #----get a list of all days within the targeted period range----
                        all_days = noise_module.get_event_list(start_date,end_date,inc_days)

                        #---------loop through the days--------
                        for ii in range(len(all_days)-1):
                            day1  = all_days[ii]
                            day2  = all_days[ii+1]
                            year1 = int(day1[:4])
                            year2 = int(day2[:4])
                            mon1  = int(day1[5:7])
                            mon2  = int(day2[5:7])
                            iday1 = int(day1[8:]) 
                            iday2 = int(day2[8:])

                            t1=obspy.UTCDateTime(year1,mon1,iday1)
                            t2=obspy.UTCDateTime(year2,mon2,iday2)
                                    
                            # sanity checks
                            if flag:
                                print(K.code + "." + sta.code + "." + chan.code+' at '+str(t1)+'.'+str(t2))
                            
                            try:
                                # get data
                                t0=time.time()
                                tr = client.get_waveforms(network=K.code, station=sta.code, channel=chan.code, location='*', \
                                    starttime = t1, endtime=t2)
                                t1=time.time()

                            except Exception as e:
                                print(e)
                                continue
                                
                            if len(tr):
                                # clean up data
                                t2=time.time()
                                tr = noise_module.preprocess_raw(tr,sta_inv,NewFreq,checkt,pre_filt,resp,respdir)
                                t3=time.time()

                                # only keep the one with good data after processing
                                if len(tr)>0:
                                    if len(tr)==1:
                                        new_tags = tags+'_{0:04d}_{1:02d}_{2:02d}_{3}'.format(tr[0].stats.starttime.year,\
                                            tr[0].stats.starttime.month,tr[0].stats.starttime.day,chan.code.lower())
                                        ds.add_waveforms(tr,tag=new_tags)
                                    else:
                                        for ii in range(len(tr)):
                                            new_tags = tags+'_{0:04d}_{1:02d}_{2:02d}_{3}'.format(tr[ii].stats.starttime.year,\
                                                tr[ii].stats.starttime.month,tr[ii].stats.starttime.day,chan.code.lower())
                                            ds.add_waveforms(tr[ii],tag=new_tags)

                                if flag:
                                    print(ds) # sanity check
                                    print('downloading data %6.2f s; pre-process %6.2f s' % ((t1-t0),(t3-t2)))
