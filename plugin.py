"""
RONELABS Nuki smart lock plugin for Domoticz
Author: RONELABS Team,
Version:    0.0.1: alpha
            0.0.2: beta
            1.1.1: validate

"""
"""
<plugin key="1NukiSmartLock" name="1byRL-Nuki Smart Lock plugin" author="RONELABS Team" version="1.1.1">
    <params>
        <param field="Address" label="Nuki Bridge IP" width="200px" required="true" default="192.168.0.1"/>
        <param field="Port" label="Nuki Bridge Port" width="40px" required="true" default="8080"/>
        <param field="Username" label="SmartLock ID" width="200px" required="true" default="12345678"/>
        <param field="Password" label="Token" width="200px" required="true" default="123456"/>
        <param field="Mode1" label="Door sensor              (if external)" width="40px" required="false" default=""/>
        <param field="Mode2" label="Poll interval            (in minutes)" width="40px" required="true" default="10"/>
        <param field="Mode6" label="Logging Level" width="200px">
            <options>
                <option label="Normal" value="Normal"  default="true"/>
                <option label="Verbose" value="Verbose"/>
                <option label="Debug - Python Only" value="2"/>
                <option label="Debug - Basic" value="62"/>
                <option label="Debug - Basic+Messages" value="126"/>
                <option label="Debug - Connections Only" value="16"/>
                <option label="Debug - Connections+Queue" value="144"/>
                <option label="Debug - All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import json
import urllib.parse as parse
import urllib.request as request
from datetime import datetime, timedelta
import time
import base64
import itertools
import os
import subprocess as sp
from distutils.version import LooseVersion

class deviceparam:

    def __init__(self, unit, nvalue, svalue):
        self.unit = unit
        self.nvalue = nvalue
        self.svalue = svalue


class BasePlugin:

    def __init__(self):

        self.debug = False
        self.statussupported = True
        # Nuki SM Actions - 1=unlock, 2=lock, 3=unlatch
        self.NukiSMaction = 0
        self.DoorContact = []
        self.NukiLastCallBack = datetime.now() - timedelta(minutes=60)
        self.Poll = 10
        return


    def onStart(self):

        # setup the appropriate logging level
        try:
            debuglevel = int(Parameters["Mode6"])
        except ValueError:
            debuglevel = 0
            self.loglevel = Parameters["Mode6"]
        if debuglevel != 0:
            self.debug = True
            Domoticz.Debugging(debuglevel)
            DumpConfigToLog()
            self.loglevel = "Verbose"
        else:
            self.debug = False
            Domoticz.Debugging(0)

        # Creating the widgets
        devicecreated = []
        if 1 not in Devices:
            Domoticz.Device(Name="Door State", Unit=1, Type=244, Subtype=73, Switchtype=11, Used=1).Create()
            devicecreated.append(deviceparam(1, 0, ""))  # default is Closed
        if 2 not in Devices:
            Domoticz.Device(Name="Lock", Unit=2, Type=244, Subtype=73, Switchtype=19, Used=1).Create()
            devicecreated.append(deviceparam(2, 0, ""))  # default is Locked
        if 3 not in Devices:
            Domoticz.Device(Name="unlatch", Unit=3, Type=244, Subtype=73, Switchtype=9, Used = 1).Create()
            devicecreated.append(deviceparam(3, 0, ""))  # default is Off
        if 4 not in Devices:
            Domoticz.Device(Name="Smart Lock Battery", Unit=4, Type=243, Subtype=6, Used=1).Create()
            devicecreated.append(deviceparam(4, 0, ""))  # default is 0

        # if any device has been created in onStart(), now is time to update its defaults
        for device in devicecreated:
            Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

        # Set polling interval
        self.Poll = int(Parameters["Mode2"])
        Domoticz.Debug("Setted poll interval : {} minute(s)".format(self.Poll))

        # build lists of external door contacts if there is some
        if not Parameters["Mode1"] == "":
            self.DoorContact = parseCSV(Parameters["Mode1"])
            Domoticz.Debug("External door contact = {}".format(self.DoorContact))

# Plugin STOP  --------------------------------------------------------

    def onStop(self):
        Domoticz.Debugging(0)

# DZ Widget actions  ---------------------------------------------------

    def onCommand(self, Unit, Command, Level, Color):

        Domoticz.Debug("onCommand called for Unit {}: Command '{}', Level: {}".format(Unit, Command, Level))

        # Nuki SM Actions - 1=unlock, 2=lock, 3=unlatch
        if (Unit == 2):  # Lock-Unlock
            Devices[2].Update(nValue = Devices[2].nValue, sValue = Devices[2].sValue)
            if (Devices[2].nValue == 1):
                self.NukiSMaction = 1
                Domoticz.Debug("Unlocking Smart Lock")
                Devices[2].Update(nValue=0, sValue="Unlocked")
            else :
                self.NukiSMaction = 2
                Domoticz.Debug("Locking Smart Lock")
                Devices[2].Update(nValue=1, sValue="Locked")

        if (Unit == 3): # Unlatch
            self.NukiSMaction = 3
            Domoticz.Debug("Unlatch pushed")
            Devices[2].Update(nValue=0, sValue="Unlocked")
            
        NukicontrolAPI("{}".format(self.NukiSMaction))
        # Restetting call back time
        self.NukiLastCallBack = now

# Heartbeat  ---------------------------------------------------

    def onHeartbeat(self):

        Domoticz.Debug("Heartbeat called")

        now = datetime.now()

        # fool proof checking.... based on users feedback
        if not all(device in Devices for device in (1, 2, 3, 4)):
            Domoticz.Error("one or more devices required by the plugin is/are missing, please check domoticz device creation settings and restart !")
            return

        # Updating Nuki Smart Lock States and DZ widgets
        if self.NukiLastCallBack + timedelta(minutes=self.Poll) <= now  :
            Domoticz.Debug("---- Nuki Call Back")
            self.NukiLastCallBack = now
            NukiSMcheckAPI("")



# Global def---------------------------------------------------

global _plugin
_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

# Nuki Smart Lock API  ---------------------------------------------------

# Check Nuki Smart Lock State  ---
    
def NukiSMcheckAPI(APICall):

    resultJson = None
    url = "http://{}:{}/lockState?nukiId={}&deviceType=0&token={}{}".format(Parameters["Address"], Parameters["Port"], Parameters["Username"], Parameters["Password"], parse.quote(APICall, safe="&="))
    Domoticz.Debug("Calling Nuki SM check API: {}".format(url))
    try:
        req = request.Request(url)
        response = request.urlopen(req)
        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson["success"] != True:
                Domoticz.Error("NUKI API returned an error: Success = {}".format(resultJson["success"]))
                resultJson = None
            else:
                Domoticz.Debug("Nuki API reply : Success = {}".format(resultJson["success"]))
            """
            # Updating Nuki SM State
            SMdoorstate = resultJson["doorsensorState"]
            SMlockstate = resultJson["state"]
            SMbatt = resultJson["batteryChargeState"]
            # Updating DZ Widget according to Nuki SM State response
            # Door State
            if Parameters["Mode1"] == "":
                if SMdoorstate == 2 :
                    Devices[1].Update(nValue=0, sValue="Closed")
                elif SMdoorstate = 3 :
                    Devices[1].Update(nValue=1, sValue="Open")
                else :
                    Domoticz.Error("Nuki SM API response : DOOR state unknown")
                    Devices[1].Update(nValue=1, sValue="Open")
            # LockState
            if SMlockstate = 1 :
                Devices[2].Update(nValue=1, sValue="Locked")
            elif SMlockstate = 2 :
                Devices[2].Update(nValue=0, sValue="Unlocked")
            else:
                Domoticz.Error("Nuki SM API response : LOCK state unknown")
                Devices[2].Update(nValue=0, sValue="Unlocked")
            # BatteryState
            Devices[4].Update(nValue= 0, sValue=str(SMbatt))
            """
        else:
            Domoticz.Error("Nuki SM API: http error = {}".format(response.status))

    except:
        Domoticz.Log("XXXXXXXXX ---------------------> Nuki SM seems not connected !")

    return resultJson

# Nuki Smart Lock  Control ---

def NukicontrolAPI(APICall):

    resultJson = None
    url = "http://{}:{}/lockAction?nukiId={}&deviceType=0&token={}&action={}".format(Parameters["Address"], Parameters["Port"], Parameters["Username"], Parameters["Password"], parse.quote(APICall, safe="&="))
    Domoticz.Debug("Calling Nuki SM control API: {}".format(url))
    try:
        req = request.Request(url)
        response = request.urlopen(req)
        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson["success"] != True:
                Domoticz.Error("NUKI API returned an error: Success = {}".format(resultJson["success"]))
                resultJson = None
            else :
                Domoticz.Debug("Nuki API reply : Success = {}".format(resultJson["success"]))
        else:
            Domoticz.Error("NUKI API: http error = {}".format(response.status))
    except:
        Domoticz.Error("Error calling '{}'".format(url))
    return resultJson

# Plugin utility functions ---------------------------------------------------

def parseCSV(strCSV):
    listvals = []
    for value in strCSV.split(","):
        try:
            val = int(value)
        except:
            pass
        else:
            listvals.append(val)
    return listvals

def CheckParam(name, value, default):
    try:
        param = int(value)
    except ValueError:
        param = default
        Domoticz.Error("Readed '{}' has an invalid value of '{}' ! defaut of '{}' is instead used.".format(name, value, default))
    return param

# Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return