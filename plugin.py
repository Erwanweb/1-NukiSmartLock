"""
RONELABS's Nuki smart lock plugin for Domoticz
Author: RONELABS Team,
Version:    0.0.1: alpha
            0.0.2: beta
            1.1.1: validate

"""
"""
<plugin key="1NukiSmartLock" name="1byRL-Nuki Smart Lock plugin" author="RONELABS Team" version="1.1.1">
    <description>
        <h2>RONELABS's Nuki smart lock plugin for Domoticz</h2><br/>
        Easily implement in Domoticz control of Nuki Smart Lock<br/>
        <br/>
        Important : Please note that nuki locks drain batteries fast if polling is set too low<br/>
        So, Since the lock status is updated on start and the lock shouldn't get out of sync<br/>
        as long as the plugin runs a short polling time should not be required<br/>
        Recommended polling interval : Between 10 to 15 mins<br/>
        <br/>
        <h3>Set-up and Configuration</h3>
        <br/> 
    </description>
    <params>
        <param field="Address" label="Nuki Bridge IP" width="100px" required="true" default="192.168.0.1"/>
        <param field="Port" label="Nuki Bridge Port" width="40px" required="true" default="8080"/>
        <param field="Username" label="SmartLock ID" width="100px" required="true" default="12345678"/>
        <param field="Password" label="Token" width="100px" required="true" default="123456"/>
        <param field="Mode1" label="Door sensor (if external)" width="40px" required="true" default=""/>
        <param field="Mode2" label="Poll interval (in minutes)" width="40px" required="true" default="10"/>
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
import requests
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
        self.PSactif = False
        self.NukiLastCallBack = datetime.now() - timedelta(minutes=60)
        self.Poll = 10
        self.SMlockstate = 2
        self.SMbatt = 0
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
        self.DoorContact = parseCSV(Parameters["Mode1"])
        Domoticz.Debug("External door contact = {}".format(self.DoorContact))

# Plugin STOP  --------------------------------------------------------

    def onStop(self):
        Domoticz.Debugging(0)

# DZ Widget actions  ---------------------------------------------------

    def onCommand(self, Unit, Command, Level, Color):

        Domoticz.Debug("onCommand called for Unit {}: Command '{}', Level: {}".format(Unit, Command, Level))
        now = datetime.now()

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
            checkAPI = NukiSMcheckAPI("")
            if checkAPI :
                Domoticz.Debug("Checking SL API ...")
                self.SMlockstate = checkAPI["state"]
                self.SMbatt = checkAPI["batteryChargeState"]
                Domoticz.Debug("SL API  Response : Lock state = {}, and Batt. = {} %".format(self.SMlockstate,self.SMbatt))
                # Updating DZ Widget according to Nuki SM State response
                # LockState
                if self.SMlockstate == 1:
                    Devices[2].Update(nValue=1, sValue="Locked")
                elif self.SMlockstate == 3:
                    Devices[2].Update(nValue=0, sValue="Unlocked")
                else:
                    Domoticz.Error("Nuki SL API response : LOCK state unknown")
                    Devices[2].Update(nValue=0, sValue="Unlocked")
                # BatteryLevel
                Devices[4].Update(nValue=0, sValue=str(self.SMbatt))
                Domoticz.Debug("... DZ NUKI SM Widget values updated")
        # Door State
        Domoticz.Debug("Checking door state")
        self.PSactif = False
        devicesAPI = DomoticzAPI("type=command&param=getdevices&filter=light&used=true&order=Name")
        if devicesAPI:
            for device in devicesAPI["result"]:  # parse the switch device
                idx = int(device["idx"])
                if idx in self.DoorContact:  # this switch is one of our heaters
                    if "Status" in device:
                        Domoticz.Debug("Verif : PS Sensor idx {}, currently is '{}'".format(idx, device["Status"]))
                        #Domoticz.Debug("Door state checked")
                        if not device["Status"] == "Off":
                            if not device["Status"] == "Closed":
                                self.PSactif = True
                        if not device["Status"] == "Closed":
                            if not device["Status"] == "Off":
                                self.PSactif = True
                    else:
                        Domoticz.Error("the devices idx in the 'door sensor' parameter is a door sensor !")

        if self.PSactif :
            Devices[1].Update(nValue=1, sValue="Open")
        else :
            Devices[1].Update(nValue=0, sValue="Closed")



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


# DOMOTICZ API AND OTHER DEF  ---------------------------------------------------

def parseCSV(strCSV):
    listvals = []
    for value in strCSV.split(","):
        try:
            val = int(value)
            listvals.append(val)
        except ValueError:
            try:
                val = float(value)
                listvals.append(val)
            except ValueError:
                Domoticz.Error(f"Skipping non-numeric value: {value}")
    return listvals


def DomoticzAPI(APICall):
    resultJson = None
    url = f"http://127.0.0.1:8080/json.htm?{parse.quote(APICall, safe='&=')}"

    try:
        Domoticz.Debug(f"Domoticz API request: {url}")
        req = request.Request(url)
        response = request.urlopen(req)

        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson.get("status") != "OK":
                Domoticz.Error(f"Domoticz API returned an error: status = {resultJson.get('status')}")
                resultJson = None
        else:
            Domoticz.Error(f"Domoticz API: HTTP error = {response.status}")

    except urllib.error.HTTPError as e:
        Domoticz.Error(f"HTTP error calling '{url}': {e}")

    except urllib.error.URLError as e:
        Domoticz.Error(f"URL error calling '{url}': {e}")

    except json.JSONDecodeError as e:
        Domoticz.Error(f"JSON decoding error: {e}")

    except Exception as e:
        Domoticz.Error(f"Error calling '{url}': {e}")

    return resultJson



def CheckParam(name, value, default):
    try:
        param = int(value)
    except ValueError:
        param = default
        Domoticz.Error( f"Parameter '{name}' has an invalid value of '{value}' ! defaut of '{param}' is instead used.")
    return param


# Nuki Smart Lock API  ---------------------------------------------------

# Check Nuki Smart Lock State  ---
    
def NukiSMcheckAPI(APICall):

    Domoticz.Log("Calling Nuki SM check API")
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
                Domoticz.Debug("Nuki API reply : Success = {}, Lock state = {}, and Batt. = {} %".format(resultJson["success"], resultJson["state"], resultJson["batteryChargeState"]))
        else:
            Domoticz.Error("Nuki SM API: http error = {}".format(response.status))

    except urllib.error.HTTPError as e:
        Domoticz.Error(f"HTTP error calling '{url}': {e}")

    except urllib.error.URLError as e:
        Domoticz.Error(f"URL error calling '{url}': {e}")

    except json.JSONDecodeError as e:
        Domoticz.Error(f"JSON decoding error: {e}")

    except Exception as e:
        Domoticz.Error(f"Error calling '{url}': {e}")

    return resultJson

# Nuki Smart Lock  Control ---

def NukicontrolAPI(APICall):

    Domoticz.Log("Calling Nuki SM Control API")
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
            
    except urllib.error.HTTPError as e:
        Domoticz.Error(f"HTTP error calling '{url}': {e}")

    except urllib.error.URLError as e:
        Domoticz.Error(f"URL error calling '{url}': {e}")

    except json.JSONDecodeError as e:
        Domoticz.Error(f"JSON decoding error: {e}")

    except Exception as e:
        Domoticz.Error(f"Error calling '{url}': {e}")
        
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