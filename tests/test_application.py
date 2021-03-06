# -*- coding: utf-8 -*-
"""Tests for the main app."""

from __future__ import (
    absolute_import, division, print_function, unicode_literals,
)

import itertools
import json
import logging
import os
import subprocess
from unittest import TestCase

import jupyter_core.paths
import nose.tools as nt
from jupyter_contrib_core.notebook_compat import nbextensions
from jupyter_contrib_core.testing_utils import (
    get_logger, patch_traitlets_app_logs,
)
from jupyter_contrib_core.testing_utils.jupyter_env import patch_jupyter_dirs
from traitlets.config import Config
from traitlets.tests.utils import check_help_all_output, check_help_output

from jupyter_contrib_nbextensions.application import main as main_app
from jupyter_contrib_nbextensions.application import (
    BaseContribNbextensionsApp, BaseContribNbextensionsInstallApp,
    ContribNbextensionsApp, InstallContribNbextensionsApp,
    UninstallContribNbextensionsApp,
)

app_classes = (
    BaseContribNbextensionsApp, BaseContribNbextensionsInstallApp,
    ContribNbextensionsApp,
    InstallContribNbextensionsApp, UninstallContribNbextensionsApp,
)


class AppTest(TestCase):
    """Tests for the main app."""

    @classmethod
    def setup_class(cls):
        cls.log = cls.log = get_logger(cls.__name__)
        cls.log.handlers = []
        cls.log.propagate = True

    def setUp(self):
        """Set up test fixtures for each test."""
        (jupyter_patches, self.jupyter_dirs,
         remove_jupyter_dirs) = patch_jupyter_dirs()
        for ptch in jupyter_patches:
            ptch.start()
            self.addCleanup(ptch.stop)
        self.addCleanup(remove_jupyter_dirs)
        for klass in app_classes:
            patch_traitlets_app_logs(klass)
            klass.log_level.default_value = logging.DEBUG

    def _check_install(self, dirs):
        installed_files = []
        for tree_dir in dirs.values():
            in_this_tree = []
            for root, subdirs, files in os.walk(tree_dir, followlinks=True):
                in_this_tree.extend([os.path.join(root, f) for f in files])
            nt.assert_true(
                in_this_tree,
                'Install should create file(s) in {}'.format(*dirs.values()))
            installed_files.extend(in_this_tree)

        return installed_files

    def _check_uninstall(self, dirs, installed_files):
        # check that nothing remains in the data directory
        data_installed = [
            path for path in installed_files
            if path.startswith(dirs['data']) and os.path.exists(path)]
        nt.assert_false(
            data_installed,
            'Uninstall should remove all data files from {}'.format(
                dirs['data']))
        # check the config directory
        conf_installed = [
            path for path in installed_files
            if path.startswith(dirs['conf']) and os.path.exists(path)]
        for path in conf_installed:
            with open(path, 'r') as f:
                conf = Config(json.load(f))
            confstrip = {}
            confstrip.update(conf)
            confstrip.pop('NotebookApp', None)
            confstrip.pop('version', None)
            nt.assert_false(confstrip, 'disable should leave config empty.')

    def _get_default_check_kwargs(self, argv, dirs):
        if argv is None:
            argv = []
        if dirs is None:
            dirs = {
                'conf': jupyter_core.paths.jupyter_config_dir(),
                'data': jupyter_core.paths.jupyter_data_dir(),
            }
        return argv, dirs

    def _call_main_app(self, argv):
        main_app(argv=argv)
        # a bit of a hack to allow initializing a new app instance
        for klass in app_classes:
            klass.clear_instance()

    def _check_subproc(self, args):
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            output, unused_err = proc.communicate()
        except:
            proc.kill()
            proc.wait()
            raise
        print(output.decode())  # this gets it captured by nose
        retcode = proc.poll()
        nt.assert_equal(retcode, 0, 'command should exit with code 0')

    def check_app_install(self, argv=None, dirs=None):
        """Check files were installed in the correct place."""
        argv, dirs = self._get_default_check_kwargs(argv, dirs)
        self._call_main_app(argv=['install'] + argv)
        installed_files = self._check_install(dirs)
        self._call_main_app(argv=['uninstall'] + argv)
        self._check_uninstall(dirs, installed_files)

    def check_cli_install(self, argv=None, dirs=None,
                          app_name='jupyter contrib nbextension'):
        argv, dirs = self._get_default_check_kwargs(argv, dirs)
        args = app_name.split(' ') + ['install'] + argv
        self._check_subproc(args)
        installed_files = self._check_install(dirs)
        args = app_name.split(' ') + ['uninstall'] + argv
        self._check_subproc(args)
        self._check_uninstall(dirs, installed_files)

    def test_00_extra_args(self):
        """Check that app complains about extra args."""
        for subcom in ('install', 'uninstall'):
            # sys.exit should be called if extra args specified
            with nt.assert_raises(SystemExit):
                main_app([subcom, 'arbitrary_extension_name'])
            for klass in app_classes:
                klass.clear_instance()

    def test_01_help_output(self):
        """Check that app help works."""
        app_module = 'jupyter_contrib_nbextensions.application'
        for subcommand in (None, ['install'], ['uninstall']):
            check_help_output(app_module, subcommand=subcommand)
            check_help_all_output(app_module, subcommand=subcommand)
        # sys.exit should be called if empty argv specified
        with nt.assert_raises(SystemExit):
            main_app([])

    def test_02_argument_conflict(self):
        """Check that install objects to multiple flags."""
        conflicting_flags = ('--user', '--system', '--sys-prefix')
        conflicting_flagsets = []
        for nn in range(2, len(conflicting_flags) + 1):
            conflicting_flagsets.extend(
                itertools.combinations(conflicting_flags, nn))
        for subcommand in ('install', 'uninstall'):
            for flagset in conflicting_flagsets:
                self.log.info('testing conflicting flagset {}'.format(flagset))
                nt.assert_raises(nbextensions.ArgumentConflict,
                                 main_app, [subcommand] + list(flagset))

    def test_03_app_install_defaults(self):
        """Check that app install works correctly using defaults."""
        self.check_app_install()

    def test_04_cli_install_defaults(self):
        """Check that cli install works correctly using defaults."""
        self.check_cli_install()

    def test_05_app_install_user(self):
        """Check that app install works correctly using --user flag."""
        self.check_app_install(argv=['--user'])

    def test_06_cli_install_user(self):
        """Check that cli install works correctly using --user flag."""
        self.check_cli_install(argv=['--user'])

    def test_07_app_install_sys_prefix(self):
        """Check that app install works correctly using --sys-prefix flag."""
        self.check_app_install(
            dirs=self.jupyter_dirs['sys_prefix'], argv=['--sys-prefix'])

    # don't test cli install with --sys-prefix flag, as we can't patch
    # directories in the subprocess

    def test_08_app_install_system(self):
        """Check that app install works correctly using --system flag."""
        self.check_app_install(
            dirs=self.jupyter_dirs['system'], argv=['--system'])

    # don't test cli install with --system flag, as we can't patch
    # directories in the subprocess

    def test_09_app_install_symlink(self):
        """Check that app install works correctly using --symlink flag."""
        self.check_app_install(argv=['--symlink'])

    def test_10_cli_install_symlink(self):
        """Check that cli install works correctly using --symlink flag."""
        self.check_cli_install(argv=['--symlink'])

    def test_11_app_install_nbextensions_dir(self):
        """Check that app install works correctly using --nbextensions arg."""
        self.check_app_install(
            dirs={'conf': self.jupyter_dirs['system']['conf'],
                  'data': self.jupyter_dirs['custom']['data'], },
            # we need to set user flag false to avoid ArgumentConflict
            argv=[
                '--BaseContribNbextensionsInstallApp.user=False',
                '--nbextensions={}'.format(
                    os.path.join(
                        self.jupyter_dirs['custom']['data'], 'nbextensions'))])

    # We can't test cli install using nbextensions_dir, since it edits system
    # config, and we can't patch directories in the subprocess

    def test_12_app_plural_alias(self):
        """Check that app works correctly when using 'nbextensions' plural."""
        self.check_cli_install(
            argv=['--user'], app_name='jupyter contrib nbextensions')
