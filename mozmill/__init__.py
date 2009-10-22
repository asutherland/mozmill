# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Mozilla Corporation Code.
#
# The Initial Developer of the Original Code is
# Mikeal Rogers.
# Portions created by the Initial Developer are Copyright (C) 2008
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#  Mikeal Rogers <mikeal.rogers@gmail.com>
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****

import os
import sys
import copy
import socket
import imp
import traceback
from datetime import datetime, timedelta
try:
    import json
except:
    import simplejson as json

import logging
logger = logging.getLogger('mozmill')

import jsbridge
from jsbridge.network import JSBridgeDisconnectError
import mozrunner

from time import sleep

basedir = os.path.abspath(os.path.dirname(__file__))

extension_path = os.path.join(basedir, 'extension')

appInfoJs = "Components.classes['@mozilla.org/xre/app-info;1'].getService(Components.interfaces.nsIXULAppInfo)"

class LoggerListener(object):
    cases = {
        'mozmill.pass':   lambda obj: logger.debug('Test Pass: '+repr(obj)),
        'mozmill.fail':   lambda obj: logger.error('Test Failure: '+repr(obj)),
        'mozmill.skip':   lambda obj: logger.info('Test Skipped: ' +repr(obj))
    }
    
    class default(object):
        def __init__(self, eName): self.eName = eName
        def __call__(self, obj): logger.info(self.eName+' :: '+repr(obj))
    
    def __call__(self, eName, obj):
        if self.cases.has_key(eName):
            self.cases[eName](obj)
        else:
            self.cases[eName] = self.default(eName)
            self.cases[eName](obj)

class MozMill(object):
    endRunnerCalled = False
    
    def __init__(self, runner_class=mozrunner.FirefoxRunner, 
                 profile_class=mozrunner.FirefoxProfile, jsbridge_port=24242):
        self.runner_class = runner_class
        self.profile_class = profile_class
        self.jsbridge_port = jsbridge_port
        self.passes = [] ; self.fails = [] ; self.skipped = []
        self.alltests = []
    
    def add_listener(self, *args, **kwargs):
        self.back_channel.add_listener(*args, **kwargs)
    
    def add_global_listener(self, *args, **kwargs):
        self.back_channel.add_global_listener(*args, **kwargs)
    
    def start(self, profile=None, runner=None):
        if not profile:
            profile = self.profile_class(plugins=[jsbridge.extension_path, extension_path])
        if not runner:
            runner = self.runner_class(profile=self.profile, 
                                       cmdargs=["-jsbridge", str(self.jsbridge_port)])
        
        self.profile = profile; self.runner = runner
        self.runner.start()
        
        self.back_channel, self.bridge = jsbridge.wait_and_create_network("127.0.0.1", self.jsbridge_port)
    
    def run_tests(self, test, report=False, sleeptime=4):
        
        self.add_listener(self.endTest_listener, eventType='mozmill.endTest')
        self.add_listener(self.endRunner_listener, eventType='mozmill.endRunner')

        frame = jsbridge.JSObject(self.bridge, "Components.utils.import('resource://mozmill/modules/frame.js')")
        sleep(sleeptime)
        starttime = datetime.utcnow().isoformat()
        
        if os.path.isdir(test):
            frame.runTestDirectory(test)
        else:
            frame.runTestFile(test)

        endtime = datetime.utcnow().isoformat()

        if report:
            appInfo = jsbridge.JSObject(self.bridge, appInfoJs)

            results = {'type':'mozmill-test', 'starttime':starttime, 
                       'endtime':endtime, 'tests':self.alltests}
            results['appInfo.id'] = str(appInfo.ID)
            results['buildid'] = str(appInfo.appBuildID)
            results['appInfo.platformVersion'] = appInfo.platformVersion
            results['appInfo.platformBuildID'] = appInfo.platformBuildID       
            sysname, nodename, release, version, machine = os.uname()
            sysinfo = {'os.name':sysname, 'hostname':nodename, 'os.version.number':release,
                       'os.version.string':version, 'arch':machine}
            if sys.platform == 'darwin':
                import platform
                sysinfo['mac_ver'] = platform.mac_ver()
            elif sys.platform == 'linux2':
                import platform
                sysinfo['linux_distrobution'] = platform.linux_distrobution()
                sysinfo['libc_ver'] = platform.libc_ver()           
            results['sysinfo'] = sysinfo
            
            results['testPath'] = test
            import httplib2
            http = httplib2.Http()
            response, content = http.request(report, 'POST', body=json.dumps(results))
        
        # Give a second for any callbacks to finish.
        sleep(1)
        
    def endTest_listener(self, test):
        self.alltests.append(test)
        if test.get('skipped', False):
            print 'Test Skipped : '+test['name']+' | '+test.get('skipped_reason', '')
            self.skipped.append(test)
        elif test['failed'] > 0:
            print 'Test Failed : '+test['name']+' in '+test['filename']
            self.fails.append(test)
        else:
            self.passes.append(test)

    def endRunner_listener(self, obj):
        print 'Passed '+str(len(self.passes))+' :: Failed '+str(len(self.fails))+' :: Skipped '+str(len(self.skipped))
        self.endRunnerCalled = True

    def stop(self, timeout=10):
        sleep(1)
        mozmill = jsbridge.JSObject(self.bridge, "Components.utils.import('resource://mozmill/modules/mozmill.js')")
        try:
            mozmill.cleanQuit()
        except (socket.error, JSBridgeDisconnectError):
            pass
        self.runner.wait()
        self.back_channel.close()
        self.bridge.close()
        x = 0
        while self.endRunnerCalled is False and x != timeout:
            sleep(1); x += 1
        if timeout == x:
            print "endRunner was never called. There must have been a failure in the framework."
            self.runner.profile.cleanup()
            sys.exit(1)

class MozMillRestart(MozMill):
    
    def __init__(self, *args, **kwargs):
        super(MozMillRestart, self).__init__(*args, **kwargs)
        self.listeners = []
        self.global_listeners = []
        self.python_callbacks = []
    
    def add_listener(self, callback, **kwargs):
        self.listeners.append((callback, kwargs,))
    def add_global_listener(self, callback):
        self.global_listeners.append(callback)
    
    def start(self, runner=None, profile=None):
        if not profile:
            profile = self.profile_class(plugins=[jsbridge.extension_path, extension_path])
        if not runner:
            runner = self.runner_class(profile=self.profile, 
                                       cmdargs=["-jsbridge", str(self.jsbridge_port)])
        
        self.profile = profile; self.runner = runner
    
    def fire_python_callback(self, method, arg):
        meth = getattr(self.python_callbacks_module, method)
        try:
            meth(arg)
        except Exception, e:
            self.endTest_listener({"name":method, "failed":1, 
                                   "python_exception_type":e.__class__.__name__,
                                   "python_exception_string":str(e),
                                   "python_traceback":traceback.format_exc(),
                                   "filename":self.python_callbacks_module.__file__})
            return False
        self.endTest_listener({"name":method, "failed":0, 
                               "filename":self.python_callbacks_module.__file__})
        return True
    
    def firePythonCallback_listener(self, obj):
        if obj['fire_now']:
            self.fire_python_callback(obj['method'], obj['arg'])
        else:
            self.python_callbacks.append(obj)
        
    def start_runner(self):
        self.runner.start()
        back_channel, bridge = jsbridge.wait_and_create_network("127.0.0.1", self.jsbridge_port)
        
        for listener in self.listeners:
            back_channel.add_listener(listener[0], **listener[1])
        for global_listener in self.global_listeners:
            back_channel.add_global_listener(global_listener)
        
        self.back_channel = back_channel
        self.endRunnerCalled = False
        
        frame = jsbridge.JSObject(bridge, "Components.utils.import('resource://mozmill/modules/frame.js')")
        self.bridge = bridge
        return frame
    
    def stop_runner(self):
        sleep(1)
        
        mozmill = jsbridge.JSObject(self.bridge, "Components.utils.import('resource://mozmill/modules/mozmill.js')")
        
        try:
            mozmill.cleanQuit()
        except (socket.error, JSBridgeDisconnectError):
            pass
        # self.back_channel.close()
        # self.bridge.close()
        starttime = datetime.now()
        self.runner.wait(timeout=30)
        endtime = datetime.now()
        if ( endtime - starttime ) > timedelta(seconds=30):
            try: self.runner.stop()
            except: pass
            self.runner.wait()
        
    def endRunner_listener(self, obj):
        self.endRunnerCalled = True
    
    def persist_listener(self, obj):
        self.persisted = obj
        
    def run_dir(self, test_dir, report=False, sleeptime=4):
        if os.path.isfile(os.path.join(test_dir, 'testPre.js')):   
            pre_test = os.path.join(test_dir, 'testPre.js')
            post_test = os.path.join(test_dir, 'testPost.js') 
            if not os.path.exists(pre_test) or not os.path.exists(post_test):
                print "Skipping "+test_dir+" does not contain both pre and post test."
                return
            
            tests = [pre_test, post_test]
        else:
            if not os.path.isfile(os.path.join(test_dir, 'test1.js')):
                print "Skipping "+test_dir+" does not contain any known test file names"
                return
            tests = []
            counter = 1
            while os.path.isfile(os.path.join(test_dir, "test"+str(counter)+".js")):
                tests.append(os.path.join(test_dir, "test"+str(counter)+".js"))
                counter += 1
    
        self.add_listener(self.persist_listener, eventType="mozmill.persist")
        self.add_listener(self.endRunner_listener, eventType='mozmill.endRunner')
        
        if os.path.isfile(os.path.join(test_dir, 'callbacks.py')):
            self.python_callbacks_module = imp.load_source('callbacks', os.path.join(test_dir, 'callbacks.py'))
        
        for test in tests:
            frame = self.start_runner()
            self.endRunnerCalled = False
            sleep(sleeptime)
            if hasattr(self, 'persisted'):
                frame.persisted = self.persisted
            frame.runTestFile(test)
            while not self.endRunnerCalled:
                sleep(.25)
            self.stop_runner()
            sleep(2)
            for callback in self.python_callbacks:
                self.fire_python_callback(callback['method'], callback['arg'])
            self.python_callbacks = []
        
        self.python_callbacks_module = None    
        
        # Reset the profile.
        profile = self.runner.profile
        profile.cleanup()
        if profile.create_new:
            profile.profile = profile.create_new_profile(self.runner.binary)                
        for plugin in profile.plugins:
            profile.install_plugin(plugin)
        if jsbridge.extension_path not in profile.plugins:
            profile.install_plugin(jsbridge.extension_path)
        if extension_path not in profile.plugins:
            profile.install_plugin(extension_path)
        profile.set_preferences(profile.preferences)
    
    def run_tests(self, test_dir, report=False, sleeptime=4):
        if report:
            print 'Sorry, report is not yet implemented for restart tests.'
        test_dirs = [d for d in os.listdir(os.path.abspath(os.path.expanduser(test_dir))) 
                     if d.startswith('test') and os.path.isdir(os.path.join(test_dir, d))]
        
        self.add_listener(self.endTest_listener, eventType='mozmill.endTest')
        self.add_listener(self.firePythonCallback_listener, eventType='mozmill.firePythonCallback')
        # self.add_listener(self.endRunner_listener, eventType='mozmill.endRunner')

        if len(test_dirs) is 0:
            test_dirs = [test_dir]
                
        for d in test_dirs:
            d = os.path.abspath(os.path.join(test_dir, d))
            self.run_dir(d, report, sleeptime)
        
        profile = self.runner.profile
        profile.cleanup()
                
        class Blank(object):
            def stop(self):
                pass
        
        # Set to None to avoid calling .stop
        self.runner = None
        sleep(1) # Give a second for any pending callbacks to finish
        print 'Passed '+str(len(self.passes))+' :: Failed '+str(len(self.fails))+' :: Skipped '+str(len(self.skipped))
    
class CLI(jsbridge.CLI):
    mozmill_class = MozMill
    
    parser_options = copy.copy(jsbridge.CLI.parser_options)
    parser_options[("-t", "--test",)] = dict(dest="test", default=False, 
                                             help="Run test file or directory.")
    parser_options[("-l", "--logfile",)] = dict(dest="logfile", default=None,
                                                help="Log all events to file.")
    parser_options[("--show-errors",)] = dict(dest="showerrors", default=False, 
                                              action="store_true",
                                              help="Print logger errors to the console.")
    parser_options[("--report",)] = dict(dest="report", default=False,
                                         help="Report the results. Requires url to results server.")
    parser_options[("--showall",)] = dict(dest="showall", default=False, action="store_true",
                                         help="Show all test output.")
    
    
    def get_profile(self, *args, **kwargs):
        profile = super(CLI, self).get_profile(*args, **kwargs)
        profile.install_plugin(extension_path)
        return profile
        
    def run(self):
        runner = self.parse_and_get_runner()
        if '-foreground' not in runner.cmdargs:
            runner.cmdargs.append('-foreground')
        
        if self.options.test:
            t = os.path.abspath(os.path.expanduser(self.options.test))
            if ( not os.path.isdir(t) ) and ( not os.path.isfile(t) ):
                raise Exception("Not a valid test file/directory")
        
        m = self.mozmill_class(runner_class=mozrunner.FirefoxRunner, profile_class=mozrunner.FirefoxProfile, jsbridge_port=int(self.options.port))
        m.start(runner=runner, profile=runner.profile)
        m.add_global_listener(LoggerListener())
        if self.options.showerrors:
            outs = logging.StreamHandler()
            outs.setLevel(logging.ERROR)
            formatter = logging.Formatter("%(levelname)s - %(message)s")
            outs.setFormatter(formatter)
            logger.addHandler(outs)
        if self.options.logfile:
            logging.basicConfig(filename=self.options.logfile, 
                                filemode='w', level=logging.DEBUG)
        if ( not self.options.showall) and (
             not self.options.showerrors) and (
             not self.options.logfile):
            logging.basicConfig(level=logging.CRITICAL)
        
        if self.options.test:
            if self.options.showall:
                logging.basicConfig(level=logging.DEBUG)
                self.options.showall = False
            try:
                m.run_tests(os.path.abspath(os.path.expanduser(self.options.test)), 
                            self.options.report)
            except JSBridgeDisconnectError:
                print 'Application unexpectedly closed'
                if m.runner is not None:
                    m.runner.profile.cleanup()
                sys.exit(1)
            
            if m.runner:
                m.stop()
            if len(m.fails) > 0:
                if m.runner is not None:
                    m.runner.profile.cleanup()
                sys.exit(1)
        else:
            if self.options.shell:
                self.start_shell(runner)
            else:
                try:
                    runner.wait()
                except KeyboardInterrupt:
                    runner.stop()
        if m.runner is not None:
            m.runner.profile.cleanup()

class RestartCLI(CLI):
    parser_options = copy.copy(CLI.parser_options)
    parser_options[("-t", "--test",)] = dict(dest="test", default=False, 
                                             help="Run test directory.")
    
    mozmill_class = MozMillRestart
    
    def run(self, *args, **kwargs):
        if len(sys.argv) is 1:
            print "Restart test CLI cannot be run without arguments, try --help for usage."
            sys.exit(1)
        else:
            super(RestartCLI, self).run(*args, **kwargs)

class ThunderbirdCLI(CLI):
    profile_class = mozrunner.ThunderbirdProfile
    runner_class = mozrunner.ThunderbirdRunner

def cli():
    CLI().run()

def tbird_cli():
    ThunderbirdCLI().run()

def restart_cli():
    RestartCLI().run()
