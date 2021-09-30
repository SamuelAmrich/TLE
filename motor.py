#!/usr/bin python3
import pigpio
from time import time, sleep
from datetime import datetime
import requests
import math
from geopy import distance
# sudo pigpiod must be running for the code to function properly

class Fanta:

    def __init__(self):
        ''' GRID - list of coordinates within FOV '''
        self.DIR = 3
        self.STEP = 4
        self.MODE = (14, 15, 18)
        self.MASTER = 2
        self.SWITCH = 27
        self.CW = False
        self.CCW = True
        self.SPR = 6400
        self.freq = 2000
        self.res = '1/32'
        self.azimuth = 0
        self.RESOLUTION = {
                            'Full': (0,0,0),
                            'Half': (1,0,0),
                            '1/4': (0,1,0),
                            '1/8': (1,1,0),
                            '1/16': (0,0,1),
                            '1/32': (1,0,1)
                            }
        self.GPS = 48.95, 22.26
        self.GRID = self.generate_gps(self.GPS)

        try:
            # Connect to pigpio daemon
            self.pi = pigpio.pi()
            # Setup output pins
            self.pi.set_mode(self.DIR, pigpio.OUTPUT)
            self.pi.set_mode(self.STEP, pigpio.OUTPUT)
            # Switch setup, 1 by default, 0 when pressed. Possible EMI in homing sequence
            self.pi.set_mode(self.SWITCH, pigpio.OUTPUT)
            self.pi.write(self.SWITCH, 1)
            # Master setup, 0 by default, arming and disarming the stepper
            self.pi.set_mode(self.MASTER, pigpio.OUTPUT)
            self.pi.write(self.MASTER, 0)
            # Microstepping mode pins initiate
            for m in self.MODE:
                self.pi.set_mode(m, pigpio.OUTPUT)
            # PWM speed initiate
            self.pi.set_PWM_frequency(self.STEP, self.freq)
            for m, v in zip(self.MODE, self.RESOLUTION[self.res]):
                self.pi.write(m, v)
        except:
            print('Error occured while loading Pigpio Daemon')

    def arm(self, master, dutycycle):
        ''' sets MASTER pin to HIGH/LOW, also, disabled stepper does not get hot '''
        self.pi.set_PWM_dutycycle(self.STEP, dutycycle)
        self.pi.write(self.MASTER, master)

    def home(self):
        ''' homing sequence, redundant loop because of EMI '''
        try:
            self.arm(True, 128)
            while self.pi.read(self.SWITCH):
                self.pi.write(self.DIR, self.CCW)
                sleep(.001)
            self.arm(True, 0)
            self.azimuth = 0
        except KeyboardInterrupt:
            print('Exiting program...')
        finally:
            self.arm(True, 0)

    def rotate(self, azimuth_actual):
        ''' rotates the camera to desired azimuth_actual '''
        if azimuth_actual == 0:
            self.home()
        elif self.azimuth < azimuth_actual < 255:
            self.arm(True, 128)
            for i in range(int((self.SPR / 360) * (azimuth_actual - self.azimuth))):
                self.pi.write(self.DIR, self.CW)
                sleep(.0017)
            self.azimuth = azimuth_actual
        elif azimuth_actual < self.azimuth and azimuth_actual < 255:
            self.arm(True, 128)
            for i in range(int((self.SPR / 360) * (self.azimuth - azimuth_actual))):
                self.pi.write(self.DIR, self.CCW)
                sleep(.0017)
            self.azimuth = azimuth_actual
        else:
            pass
        #Change this to True in real operation
        self.arm(True, 0)

    def true_bearing(self, a, b):
        ''' a,b are tuples of coordinates (lat, lon), function returns bearing to b as seen from a, great circle method '''
        a = [math.radians(i) for i in a]
        b = [math.radians(i) for i in b]
        s = math.cos(b[0]) * math.sin(abs(b[1] - a[1]))
        c = math.cos(a[0]) * math.sin(b[0]) - math.sin(a[0]) * math.cos(b[0]) * math.cos(abs(b[1] - a[1]))
        result = math.degrees(math.atan2(s, c))
        return int((result + 360) % 360)

    def true_distance(self, a, b):
        ''' a,b are tuples of coordinates (lat, lon), function returns their distance in km '''
        return round(distance.geodesic(a, b).km, 2)

    def generate_gps(self, gps):
        ''' creates and returns a list, grid of gps (lat, lon) tuples within a radius in km from initial gps coords. Temporary variables responsible for spacing of the final coord grid'''
        temp = {}
        lat_it = 50
        lon_it = 50
        incr = .3
        min_fov = 50
        max_fov = 600
        for lat in range(lat_it):
            for lon in range(lon_it):
                ''' North-East '''
                gps_new = (round(gps[0] + (lat * incr), 2), round(gps[1] + (lon * incr), 2))
                if min_fov < self.true_distance(gps, gps_new) < max_fov:
                    temp[((gps_new[0], gps_new[1]))] = self.true_distance(gps, gps_new)
        for lat in range(lat_it):
            for lon in range(lon_it):
                ''' South-East '''
                gps_new = (round(gps[0] - (lat * incr), 2), round(gps[1] + (lon * incr), 2))
                if min_fov < self.true_distance(gps, gps_new) < max_fov:
                    temp[((gps_new[0], gps_new[1]))] = self.true_distance(gps, gps_new)
        return [k for k, v in sorted(temp.items(), key=lambda item: item[1])]

    def storm_api_check(self, gps):
        ''' returns tuple containing True confirming parameter, weather status, 2 thunderstorm, 5** heavy rains '''
        r = requests.get("https://api.openweathermap.org/data/2.5/weather?lat={}&lon={}&appid=53a4c66814d54b4d9cb3ff3b5c013d86".format(gps[0], gps[1])).json()
        id = r['weather'][0]['id']
        valid = 200, 201, 202, 210, 211, 212, 221, 230, 231, 232, 502, 503, 504, 511, 522, 531
        if id in valid:
            print(id)
            return True, id

    def sweep(self, grid):
        ''' returns a bearing to single closest storm '''
        results = {}
        print('Fetching API data... ')
        for gps in grid:
            try:
                interim = self.storm_api_check(gps)
                if interim[0]:
                    results[self.true_distance(self.GPS, gps)] = gps, self.true_bearing(self.GPS, gps), interim[1]
            except:
                continue
        if len(results) != 0:
            closest_storm = min(results.keys())
            res = [bearing for key, bearing in results.items() if key == closest_storm]
            self.save(res[0][0], res[0][2])
            return res[0][1]
        else:
            print('No current active storms within the FOV')
            return 0

    def save(self, gps, id):
        ''' Saves relevant data into a log file '''
        now = datetime.utcnow()
        try:
            with open('{}_log.csv'.format(datetime.utcnow().strftime("%Y_%b")), 'a') as f:
                f.write(str(datetime.timestamp(now)) + ', ' + str(gps[0]) + ', ' + str(gps[1]) + ', ' + str(id) + ',\n')
        except:
            with open('{}_log.csv'.format(datetime.utcnow().strftime("%Y_%b")), 'w') as f:
                f.write(str(datetime.timestamp(now)) + ', ' + str(gps) + ', ' + str(gps[1]) + ', ' + str(id) + ',\n')

    def automatic(self):
        ''' rotates to an active storm '''
        try:
            self.rotate(self.sweep(self.GRID))
        except KeyboardInterrupt:
            print('Exiting program... ')
        finally:
            self.arm(False, 0)

    def switch(self):
        ''' test the switch operation '''
        try:
            while 1:
                print(self.pi.read(self.SWITCH))
                sleep(.2)
        except KeyboardInterrupt:
            print('Exiting program...')

    def boot(self):
        ''' dev '''
        try:
            self.home()
            for i in range(1):
                look_at = [45, 90, 135, 180, 225, 255]
                for log in look_at:
                    sleep(1)
                    self.rotate(log)
                sleep(1)
            self.home()
        except KeyboardInterrupt:
            print('Exiting program...')
        finally:
            self.arm(True, 0)

    def manual(self):
        ''' manual rotation to desired azimuth '''
        try:
            self.home()
            while 1:
                some_stuff = int(input('Ctrl-C to exit| Desired azimuth (0-255): '))
                sleep(1)
                self.rotate(some_stuff)
                self.azimuth = some_stuff
        except KeyboardInterrupt:
            print(f'Exiting manual mode, looking at {self.azimuth} deg.')
        finally:
            self.arm(True, 0)

