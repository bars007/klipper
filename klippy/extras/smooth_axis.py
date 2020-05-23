# Positional smoother on cartesian XY axes
#
# Copyright (C) 2019-2020  Kevin O'Connor <kevin@koconnor.net>
# Copyright (C) 2020  Dmitry Butyugin <dmbutyugin@google.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging, math
import chelper

class SmoothAxis:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.printer.register_event_handler("klippy:connect", self.connect)
        self.toolhead = None
        self.damping_ratio_x = config.getfloat(
                'damping_ratio_x', 0., minval=0., maxval=1.)
        self.damping_ratio_y = config.getfloat(
                'damping_ratio_y', 0., minval=0., maxval=1.)
        self.target_freq_x = config.getfloat('target_freq_x', 0., minval=0.)
        self.target_freq_y = config.getfloat('target_freq_y', 0., minval=0.)
        ffi_main, ffi_lib = chelper.get_ffi()
        self.smoothers = {'sifp05': ffi_lib.SIFP05
                , 'siaf05': ffi_lib.SIAF05
                , 'dfsf05': ffi_lib.DFSF05
                , 'dfaf05': ffi_lib.DFAF05
                , 'dfaf02': ffi_lib.DFAF02
                , 'dfaf01': ffi_lib.DFAF01}
        self.smoother_type = config.getchoice('smoother', self.smoothers,
                                              'sifp05')
        self.stepper_kinematics = []
        self.orig_stepper_kinematics = []
        # Register gcode commands
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command("SET_SMOOTH_AXIS",
                               self.cmd_SET_SMOOTH_AXIS,
                               desc=self.cmd_SET_SMOOTH_AXIS_help)
    def connect(self):
        self.toolhead = self.printer.lookup_object("toolhead")
        kin = self.toolhead.get_kinematics()
        # Lookup stepper kinematics
        ffi_main, ffi_lib = chelper.get_ffi()
        steppers = kin.get_steppers()
        for s in steppers:
            sk = ffi_main.gc(ffi_lib.smooth_axis_alloc(), ffi_lib.free)
            orig_sk = s.set_stepper_kinematics(sk)
            res = ffi_lib.smooth_axis_set_sk(sk, orig_sk)
            if res < 0:
                s.set_stepper_kinematics(orig_sk)
                continue
            s.set_trapq(self.toolhead.get_trapq())
            self.stepper_kinematics.append(sk)
            self.orig_stepper_kinematics.append(orig_sk)
        # Configure initial values
        self.hst_x = self.hst_y = 0.
        self._set_smoothing(self.smoother_type,
                            self.damping_ratio_x, self.damping_ratio_y,
                            self.target_freq_x, self.target_freq_y)
    def _set_smoothing(self, smoother_type
                       , damping_ratio_x, damping_ratio_y
                       , target_freq_x, target_freq_y):
        ffi_main, ffi_lib = chelper.get_ffi()
        old_smooth_time = max(self.hst_x, self.hst_y)
        self.hst_x = ffi_lib.smooth_axis_get_half_smooth_time(self.smoother_type
                , self.target_freq_x, self.damping_ratio_x)
        self.hst_y = ffi_lib.smooth_axis_get_half_smooth_time(self.smoother_type
                , self.target_freq_y, self.damping_ratio_y)
        new_smooth_time = max(self.hst_x, self.hst_y)
        self.toolhead.note_step_generation_scan_time(new_smooth_time,
                                                     old_delay=old_smooth_time)
        self.smoother_type = smoother_type
        self.damping_ratio_x = damping_ratio_x
        self.damping_ratio_y = damping_ratio_y
        self.target_freq_x = target_freq_x
        self.target_freq_y = target_freq_y
        for sk in self.stepper_kinematics:
            ffi_lib.smooth_axis_set_params(sk, smoother_type, smoother_type,
                                           target_freq_x, target_freq_y,
                                           damping_ratio_x, damping_ratio_y)
    cmd_SET_SMOOTH_AXIS_help = "Set cartesian time smoothing parameters"
    def cmd_SET_SMOOTH_AXIS(self, params):
        gcode = self.printer.lookup_object('gcode')
        damping_ratio_x = gcode.get_float(
                'DAMPING_RATIO_X', params, self.damping_ratio_x,
                minval=0., maxval=1.)
        damping_ratio_y = gcode.get_float(
                'DAMPING_RATIO_Y', params, self.damping_ratio_y,
                minval=0., maxval=1.)
        target_freq_x = gcode.get_float('TARGET_FREQ_X', params,
                                          self.target_freq_x, minval=0.)
        target_freq_y = gcode.get_float('TARGET_FREQ_Y', params,
                                          self.target_freq_y, minval=0.)
        smoother_type = self.smoother_type
        if 'SMOOTHER' in params:
            smoother_type_str = gcode.get_str('SMOOTHER', params).lower()
            if smoother_type_str not in self.smoothers:
                raise self.gcode.error(
                    "Requested smoother type '%s' is not supported" % (
                        smoother_type_str))
            smoother_type = self.smoothers[smoother_type_str]
        self._set_smoothing(smoother_type, damping_ratio_x, damping_ratio_y,
                            target_freq_x, target_freq_y)
        smoother_type_str = self.smoothers.keys()[
                self.smoothers.values().index(smoother_type)]
        gcode.respond_info("smoother_type: %s "
                           "target_freq_x:%.9f target_freq_y:%.9f "
                           "damping_ratio_x:%.9f damping_ratio_y:%.9f" % (
                               smoother_type_str, target_freq_x, target_freq_y,
                               damping_ratio_x, damping_ratio_y))

def load_config(config):
    return SmoothAxis(config)
