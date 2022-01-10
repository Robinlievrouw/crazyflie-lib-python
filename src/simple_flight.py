import logging
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander
from cflib.utils import uri_helper

URI = uri_helper.uri_from_env(default='radio://0/80/2M')
is_deck_attached = False
DEFAULT_HEIGHT = 0.5

logging.basicConfig(level=logging.ERROR)


def param_deck_flow(name, value):
    global is_deck_attached
    print(value)
    if value:
        is_deck_attached = True
        print('Deck is attached!')
    else:
        is_deck_attached = False
        print('Deck is NOT attached!')


def log_pos_callback(timestamp, data, logconf):
    print(data)


def land(scf):
    with MotionCommander(scf) as mc:
        mc.down(0.1)


def move_forward(mc):
        mc.forward(0.5)
        time.sleep(1)
        mc.forward(0.5)


def take_off_simple(mc):
        mc.up(DEFAULT_HEIGHT)


if __name__ == '__main__':

    cflib.crtp.init_drivers(enable_debug_driver=False)
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
        # Check if FlowDeck V2 added
        scf.cf.param.add_update_callback(group="deck", name="bcFlow2",
                                         cb=param_deck_flow)

        time.sleep(1)

        # Setup logging
        logconf = LogConfig(name='Position', period_in_ms=10)
        logconf.add_variable('stateEstimate.x', 'float')
        logconf.add_variable('stateEstimate.y', 'float')
        logconf.add_variable('stateEstimate.z', 'float')
        # scf.cf.log.add_config(logconf)
        # logconf.data_received_cb.add_callback(log_pos_callback)

        if is_deck_attached:
            # logconf.start()

            with MotionCommander(scf) as mc:
                take_off_simple(mc)

                mc.forward(1)
                time.sleep(0.5)
                mc.back(1)

                land(mc)
