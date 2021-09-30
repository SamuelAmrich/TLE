# sudo pigpio must be running for the code to function properly
import pigpio
from time import sleep
import requests
import math
from geopy import distance

class Soulmate:

    def __init__(self):
        ''' GRID - list of coordinates within FOV '''
        self.DIR = 20
        self.STEP = 21
        self.MODE = (14, 15, 18)
        self.MASTER = 16
        self.SWITCH = 17
        self.CW = False
        self.CCW = True
        self.SPR = 6400
        self.freq = 2000
        self.res = '1/32'
        self.azimuth = 0
        self.RESOLUTION = {
                            'Full':(0,0,0),
                            'Half':(1,0,0),
                            '1/4':(0,1,0),
                            '1/8':(1,1,0),
                            '1/16':(0,0,1),
                            '1/32':(1,0,1)
                            }
        self.GPS = (48.95,22.26)
        self.GRID = self.generate_gps(self.GPS)

        try:
            # Connect to pigpio daemon
            self.pi = pigpio.pi()
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
            for m, v in zip(self.MODE, self.RESOLUTION[str(self.res)]):
                self.pi.write(m, v)
        except:
            print('Error occured while loading Pigpio Daemon')

    def arm(self, master, dutycycle):
        ''' sets MASTER pin to HIGH/LOW, also, disabled stepper does not get hot '''
        self.pi.set_PWM_dutycycle(self.STEP, dutycycle)
        self.pi.write(self.MASTER, master)

    def home(self):
        ''' homing sequence, redundant loop because of EMI '''
        sleep(1)
        for i in range(5):
            self.arm(True, 128)
            while self.pi.read(self.SWITCH):
                self.pi.write(self.DIR, self.CCW)
                sleep(.001)
            self.arm(True, 0)
        self.azimuth = 0
        self.arm(False, 0)

    def rotate(self, azimuth_actual):
        ''' rotates the camera to desired azimuth_actual '''
        sleep(1)
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
        positions = []
        lat_it = 50
        lon_it = 50
        incr = .5
        radius = 500
        for lat in range(lat_it):
            for lon in range(lon_it):
                ''' North-East '''
                gps_new = (round(gps[0] + (lat * incr), 2), round(gps[1] + (lon * incr), 2))
                if self.true_distance(gps, gps_new) < radius:
                    positions.append((gps_new[0], gps_new[1]))
        for lat in range(lat_it):
            for lon in range(lon_it):
                ''' South-East '''
                gps_new = (round(gps[0] - (lat * incr), 2), round(gps[1] + (lon * incr), 2))
                if self.true_distance(gps, gps_new) < radius:
                    positions.append((gps_new[0], gps_new[1]))
        return positions

    def storm_api_check(self, gps):
        ''' returns tuple containing True confirming parameter, weather status, 2 thunderstorm, 5** heavy rains '''
        r = requests.get("https://api.openweathermap.org/data/2.5/weather?lat={}&lon={}&appid=53a4c66814d54b4d9cb3ff3b5c013d86".format(gps[0], gps[1])).json()
        id = r['weather'][0]['id']
        if id // 100 == 2 or id == 502 or id == 503 or id == 504:
            return True

    def sweep(self, grid):
        ''' returns a list of tuples ((lat, lon), bearing, distance) to the storms and rain respectively '''
        results = []
        print('Fetching API data... ')
        for gps in grid:
            try:
                interim = self.storm_api_check(gps)
                if interim:
                    results.append((gps, self.true_bearing(self.GPS, gps), self.true_distance(self.GPS, gps)))
            except:
                continue
        print('Data fetched successfully.')
        return results

    def store_data(self):
        ''' how often store azimuth data, what format - UTC, bearing? '''
        pass

    def automatic(self):
        ''' rotates to every active storm in 5s intervals '''
        self.home()
        active = self.sweep(self.GRID)
        if len(active) != 0:
            for storm in active:
                print('Processing data... ')
                sleep(5)
                print(f'==== lat: {storm[0][0]}, lon: {storm[0][1]}, Bearing: {storm[1]} deg, Distance: {storm[2]} km ====')
                print(storm[0])
                self.rotate(storm[1])
        else:
            print('No current active storms within the FOV')
        print('Finished with all instances... going home...')
        self.home()

    def manual(self):
        ''' custom coordinates '''
        self.home()
        look_at = [90, 180, 45, 135, 10]
        for log in look_at:
            sleep(1)
            self.rotate(log)
        self.arm(False, 0)

    def service(self):
        ''' dev '''
        while 1:
            print(self.pi.read(self.SWITCH))
            sleep(.25)

