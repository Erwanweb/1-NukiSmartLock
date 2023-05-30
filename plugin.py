"""
Nuki Smart Lock plugin for Domoticz
Author: RONELABS Team,
Version:    0.0.1: alpha
            0.0.2: beta....
"""
"""
<plugin key="1-NukiSmartLock" name="1byRL-Nuki Smart Lock plugin" author="RONELABS Team" version="0.0.2" externallink="https://github.com/Erwanweb/1-NukiSmartLock.git">
    <description>
        <h2>Nuki Smart Lock Plugin for Domoticz</h2><br/>
        Easily implement in Domoticz an full control of Nuki Smart Lock<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Address" label="Nuki Bridge local IP" width="200px" required="true" default=""/>
        <param field="Port" label="Nuki Bridge Port" width="40px" required="true" default="8080"/>
        <param field="Username" label="Nuki SmartLock ID" width="200px" required="true" default="12345678"/>
        <param field="Password" label="Token" width="200px" required="true" default="123456"/>
        <param field="Mode1" label="Door contact (if external)" required="false" default=""/>
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
import base64
import json
import itertools
import html
import requests
from distutils.version import LooseVersion

class deviceparam:

    def __init__(self, unit, nvalue, svalue):
        self.unit = unit
        self.nvalue = nvalue
        self.svalue = svalue

class BasePlugin:
        
    def __init__(self):
        # Nuki SM Actions - 1=unlock, 2=lock, 3=unlatch
        self.NukiSMaction = 0
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

        # most init ?¿?¿
        #self.__init__()

        # create the child devices if these do not exist yet
        devicecreated = []
        if 1 not in Devices:
            Domoticz.Device(Name="Door State", Unit=1, Type=244, Subtype=11, Used=1).Create()
            devicecreated.append(deviceparam(1, 0, ""))  # default is Closed
        if 2 not in Devices:
            Domoticz.Device(Name="Lock", Unit=2, TypeName="Selector Switch", ype=244, Subtype=19,  Used=1).Create()
            devicecreated.append(deviceparam(2, 0, "0"))  # default is Locked
        if 3 not in Devices:
            Domoticz.Device(Name="unlatch", Unit=3, Type=244, Subtype=9 Used=1).Create()
            devicecreated.append(deviceparam(3, 0, ""))  # default is Off
        if 4 not in Devices:
            Domoticz.Device(Name="Smart Lock Battery", Unit=4, Type=243, Subtype=6, Used=1).Create()
            devicecreated.append(deviceparam(4, 0, ""))  # default is 0

        # if any device has been created in onStart(), now is time to update its defaults
        for device in devicecreated:
            Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

# Plugin STOP  --------------------------------------------------------

    def onStop(self):
        Domoticz.Debug("onStop called")
        Domoticz.Debugging(0)

# DZ Widget actions  ---------------------------------------------------

    def onCommand(self, Unit, Command, Level, Color):
        Domoticz.Debug("onCommand called for Unit {}: Command '{}', Level: {}".format(Unit, Command, Level))

        # Nuki SM Actions - 1=unlock, 2=lock, 3=unlatch
        if (Unit == 2):  # Lock-Unlock
            Devices[2].Update(nValue = Devices[2].nvalue,sValue = Devices[2].sValue)
            if (Devices[2].nValue == 1):
                self.NukiSMaction = 1
            else :
                self.NukiSMaction = 2

        if (Unit == 3):
            Devices[3].Update(nValue = Devices[3].nvalue,sValue = Devices[3].sValue)
            if (Devices[3].nValue == 1):
                Devices[2].Update(nValue=1, Devices[2].sValue)
                self.NukiSMaction = 3

        self.NukiSMcontrolAPI()
        self.onHeartbeat()


# Heartbeat  ---------------------------------------------------

    def onHeartbeat(self):

        Domoticz.Debug("onHeartbeat called")
        # fool proof checking.... based on users feedback
        if not all(device in Devices for device in (1, 2, 3, 4)):
            Domoticz.Error("one or more devices required by the plugin is/are missing, please check domoticz device creation settings and restart !")
            return

        # Updating Nuki Smart Lock States and DZ widgets
        self.NukiSMchecktAPI()

# Check Nuki Smart Lock State  ---------------------------------------------------

    def NukiSMchecktAPI(self):

        resultJson = None
        url = "http://{}/{}/lockState?nukiId={}&deviceType=0&token={}".format(Parameters["Address"], Parameters["Port"], Parameters["Username"], Parameters["Password"])
        Domoticz.Debug("Calling Nuki SM check API: {}".format(url))
        try:
            req = request.Request(url)
            response = request.urlopen(req)
            if response.status == 200:
                resultJson = json.loads(response.read().decode('utf-8'))
                Domoticz.Debug("Nuki SM Connected -- OK")
                # Updating Nuki SM State
                SMdoorstate = remoteObject["doorsensorState"]
                SMlockstate = remoteObject["state"]
                SMbatt = remoteObject["batteryChargeState"]
                # Updating DZ Widget according to Nuki SM State response
                # Door State
                if Parameters["Mode1"] == "":
                    if SMdoorstate = 2 :
                        Devices[1].Update(nValue=0, sValue=Devices[1].sValue)
                    elif SMdoorstate = 3 :
                        Devices[1].Update(nValue=1, sValue=Devices[1].sValue)
                    else :
                        Domoticz.Error("Nuki SM API response : DOOR state unknown")
                        Devices[1].Update(nValue=1, sValue=Devices[1].sValue)
                # LockState
                if SMlockstate = 1 or SMlockstate = 4:
                    Devices[2].Update(nValue=0, sValue=Devices[2].sValue)
                elif SMlockstate = 2 or SMlockstate = 3:
                    Devices[2].Update(nValue=1, sValue=Devices[2].sValue)
                else:
                    Domoticz.Error("Nuki SM API response : LOCK state unknown")
                    Devices[2].Update(nValue=1, sValue=Devices[2].sValue)
                # BatteryState
                Devices[4].Update(nValue= 0, sValue=str(SMbatt))
            else:
                Domoticz.Error("Nuki SM API: http error = {}".format(response.status))

        except:
            Domoticz.Log("XXXXXXXXX ---------------------> Nuki SM seems not connected !")

        return resultJson

# Nuki Smart Lock Action  ---------------------------------------------------

    def NukicontrolAPI(self):

        # Nuki SM Actions - 1=unlock, 2=lock, 3=unlatch
        NSMaction = self.NukiSMaction
        resultJson = None
        url = "http://{}/{}/lockAction?nukiId={}&deviceType=0&action={}&token={}".format(Parameters["Address"], Parameters["Port"], Parameters["Username"], NSMaction, Parameters["Password"])
        Domoticz.Debug("Calling Nuki SM control API: {}".format(url))
        try:
            req = request.Request(url)
            response = request.urlopen(req)
            if response.status == 200:
                resultJson = json.loads(response.read().decode('utf-8'))
                if resultJson["success"] != "true":
                    Domoticz.Error("NUKI API returned an error: status = {}".format(resultJson["success"]))
                    resultJson = None
            else:
                Domoticz.Error("NUKI API: http error = {}".format(response.status))
        except:
            Domoticz.Error("Error calling '{}'".format(url))
        return resultJson

# Global  ---------------------------------------------------

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

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


def DomoticzAPI(APICall):

    resultJson = None
    url = "http://127.0.0.1:8080/json.htm?{}".format(parse.quote(APICall, safe="&="))
    Domoticz.Debug("Calling domoticz API: {}".format(url))
    try:
        req = request.Request(url)
        response = request.urlopen(req)
        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson["status"] != "OK":
                Domoticz.Error("Domoticz API returned an error: status = {}".format(resultJson["status"]))
                resultJson = None
        else:
            Domoticz.Error("Domoticz API: http error = {}".format(response.status))
    except:
        Domoticz.Error("Error calling '{}'".format(url))
    return resultJson

def CheckParam(name, value, default):

    try:
        param = int(value)
    except ValueError:
        param = default
        Domoticz.Error("Parameter '{}' has an invalid value of '{}' ! defaut of '{}' is instead used.".format(name, value, default))
    return param

# Generic helper functions ---------------------------------------------------

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
