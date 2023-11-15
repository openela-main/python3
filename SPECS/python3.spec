# ==================
# Top-level metadata
# ==================

Name: python3
Summary: Interpreter of the Python programming language
URL: https://www.python.org/

%global pybasever 3.6

# pybasever without the dot:
%global pyshortver 36

#  WARNING  When rebasing to a new Python version,
#           remember to update the python3-docs package as well
Version: %{pybasever}.8
Release: 56%{?dist}.openela.0
License: Python


# ==================================
# Conditionals controlling the build
# ==================================

# Note that the bcond macros are named for the CLI option they create.
# "%%bcond_without" means "ENABLE by default and create a --without option"

# Whether to use RPM build wheels from the python-{pip,setuptools}-wheel package
# Uses upstream bundled prebuilt wheels otherwise
%bcond_without rpmwheels

# Expensive optimizations (mainly, profile-guided optimizations)
%bcond_without optimizations

# Run the test suite in %%check
%bcond_without tests

# Extra build for debugging the interpreter or C-API extensions
# (the -debug subpackages)
%bcond_without debug_build

# Support for the GDB debugger
%bcond_without gdb_hooks

# The dbm.gnu module (key-value database)
%bcond_without gdbm

# Main interpreter loop optimization
%bcond_without computed_gotos

# Support for the Valgrind debugger/profiler
%ifarch %{valgrind_arches}
%bcond_without valgrind
%else
# Some arches don't have valgrind, disable support for it there.
%bcond_with valgrind
%endif

# https://fedoraproject.org/wiki/Changes/Python_Upstream_Architecture_Names
# For a very long time we have converted "upstream architecture names" to "Fedora names".
# This made sense at the time, see https://github.com/pypa/manylinux/issues/687#issuecomment-666362947
# However, with manylinux wheels popularity growth, this is now a problem.
# Wheels built on a Linux that doesn't do this were not compatible with ours and vice versa.
# We now have a compatibility layer to workaround a problem,
# but we also no longer use the legacy arch names in Fedora 34+.
# This bcond controls the behavior. The defaults should be good for anybody.
%bcond_without legacy_archnames

# ==================================
# Notes from bootstraping Python 3.6
# ==================================
#
# New Python major version (3.X) break ABI and bytecode compatibility,
# so all packages depending on it need to be rebuilt.
#
# Due to a dependency cycle between Python, gdb, rpm, pip, setuptools, wheel,
# and other packages, this isn't straightforward.
# Build in the following order:
#
# 1. At the same time:
#     - gdb without python support (add %%global _without_python 1 on top of
#       gdb's SPEC file)
#     - python-rpm-generators with bootstrapping_python set to 1
#       (this can be done also during step 2., but should be done before 3.)
# 2. python3 without rewheel (use %%bcond_with rewheel instead of
#     %%bcond_without)
# 3. At the same time:
#     - gdb with python support (remove %%global _without_python 1 on top of
#       gdb's SPEC file)
#     - python-rpm-generators with bootstrapping_python set to 0
#       (this can be done at any later step without negative effects)
# 4. rpm
# 5. python-setuptools with bootstrap set to 1
# 6. python-pip with build_wheel set to 0
# 7. python-wheel with %%bcond_without bootstrap
# 8. python-setuptools with bootstrap set to 0 and also with_check set to 0
# 9. python-pip with build_wheel set to 1
# 10. pyparsing
# 11. python3 with rewheel
#
# Then the most important packages have to be built, in dependency order.
# These were:
#   python-sphinx, pytest, python-requests, cloud-init, dnf, anaconda, abrt
#
# After these have been built, a targeted rebuild should be done for the rest.


# =====================
# General global macros
# =====================

%global pylibdir %{_libdir}/python%{pybasever}
%global dynload_dir %{pylibdir}/lib-dynload

# ABIFLAGS, LDVERSION and SOABI are in the upstream configure.ac
# See PEP 3149 for some background: http://www.python.org/dev/peps/pep-3149/
%global ABIFLAGS_optimized m
%global ABIFLAGS_debug     dm

%global LDVERSION_optimized %{pybasever}%{ABIFLAGS_optimized}
%global LDVERSION_debug     %{pybasever}%{ABIFLAGS_debug}

# When we use the upstream arch triplets, we convert them from the legacy ones
# This is reversed in prep when %%with legacy_archnames, so we keep both macros
%global platform_triplet_legacy %{_arch}-linux%{_gnu}
%global platform_triplet_upstream %{expand:%(echo %{platform_triplet_legacy} | sed -E \\
    -e 's/^arm(eb)?-linux-gnueabi$/arm\\1-linux-gnueabihf/' \\
    -e 's/^mips64(el)?-linux-gnu$/mips64\\1-linux-gnuabi64/' \\
    -e 's/^ppc(64)?(le)?-linux-gnu$/powerpc\\1\\2-linux-gnu/')}
%if %{with legacy_archnames}
%global platform_triplet %{platform_triplet_legacy}
%else
%global platform_triplet %{platform_triplet_upstream}
%endif
 
%global SOABI_optimized cpython-%{pyshortver}%{ABIFLAGS_optimized}-%{platform_triplet}
%global SOABI_debug     cpython-%{pyshortver}%{ABIFLAGS_debug}-%{platform_triplet}

# All bytecode files are in a __pycache__ subdirectory, with a name
# reflecting the version of the bytecode.
# See PEP 3147: http://www.python.org/dev/peps/pep-3147/
# For example,
#   foo/bar.py
# has bytecode at:
#   foo/__pycache__/bar.cpython-%%{pyshortver}.pyc
#   foo/__pycache__/bar.cpython-%%{pyshortver}.opt-1.pyc
#   foo/__pycache__/bar.cpython-%%{pyshortver}.opt-2.pyc
%global bytecode_suffixes .cpython-%{pyshortver}*.pyc

# Python's configure script defines SOVERSION, and this is used in the Makefile
# to determine INSTSONAME, the name of the libpython DSO:
#   LDLIBRARY='libpython$(VERSION).so'
#   INSTSONAME="$LDLIBRARY".$SOVERSION
# We mirror this here in order to make it easier to add the -gdb.py hooks.
# (if these get out of sync, the payload of the libs subpackage will fail
# and halt the build)
%global py_SOVERSION 1.0
%global py_INSTSONAME_optimized libpython%{LDVERSION_optimized}.so.%{py_SOVERSION}
%global py_INSTSONAME_debug     libpython%{LDVERSION_debug}.so.%{py_SOVERSION}

# Disable automatic bytecompilation. The python3 binary is not yet be
# available in /usr/bin when Python is built. Also, the bytecompilation fails
# on files that test invalid syntax.
%undefine py_auto_byte_compile

# For multilib support, files that are different between 32- and 64-bit arches
# need different filenames. Use "64" or "32" according to the word size.
# Currently, the best way to determine an architecture's word size happens to
# be checking %%{_lib}.
%if "%{_lib}" == "lib64"
%global wordsize 64
%else
%global wordsize 32
%endif


# =======================
# Build-time requirements
# =======================

# (keep this list alphabetized)

BuildRequires: autoconf
BuildRequires: bluez-libs-devel
BuildRequires: bzip2
BuildRequires: bzip2-devel
BuildRequires: desktop-file-utils
BuildRequires: expat-devel

BuildRequires: findutils
BuildRequires: gcc-c++
%if %{with gdbm}
BuildRequires: gdbm-devel >= 1:1.13
%endif
BuildRequires: git-core
BuildRequires: glibc-devel
BuildRequires: gmp-devel
BuildRequires: libappstream-glib
BuildRequires: libffi-devel
BuildRequires: libnsl2-devel
BuildRequires: libtirpc-devel
BuildRequires: libGL-devel
BuildRequires: libX11-devel
BuildRequires: ncurses-devel

BuildRequires: openssl-devel
BuildRequires: pkgconfig
BuildRequires: readline-devel
BuildRequires: redhat-rpm-config >= 118
BuildRequires: sqlite-devel
BuildRequires: gdb

BuildRequires: tar
BuildRequires: tcl-devel
BuildRequires: tix-devel
BuildRequires: tk-devel

%if %{with valgrind}
BuildRequires: valgrind-devel
%endif

BuildRequires: xz-devel
BuildRequires: zlib-devel

BuildRequires: /usr/bin/dtrace

# workaround http://bugs.python.org/issue19804 (test_uuid requires ifconfig)
BuildRequires: /usr/sbin/ifconfig

%if %{with rpmwheels}
BuildRequires: python3-setuptools-wheel
BuildRequires: python3-pip-wheel

# Verify that the BuildRoot includes python36.
# Not actually needed for build.
BuildRequires: python36-devel
%endif


# =======================
# Source code and patches
# =======================

# The upstream tarball includes questionable executable files for Windows,
# which we should not ship even in the SRPM.
# Run the "get-source.sh" with the version as argument to download the upstream
# tarball and generate a version with the .exe files removed. For example:
# $ ./get-source.sh 3.7.0

Source: Python-%{version}-noexe.tar.xz

# A script to remove .exe files from the source distribution
Source1: get-source.sh

# A simple script to check timestamps of bytecode files
# Run in check section with Python that is currently being built
# Written by bkabrda
Source8: check-pyc-and-pyo-timestamps.py

# Desktop menu entry for idle3
Source10: idle3.desktop

# AppData file for idle3
Source11: idle3.appdata.xml

# unversioned-python script
Source12: no-python

# unversioned-python man page
Source13: unversioned-python.1

# 00001 #
# Fixup distutils/unixccompiler.py to remove standard library path from rpath:
# Was Patch0 in ivazquez' python3000 specfile:
Patch1: 00001-rpath.patch

# 00102 #
# Change the various install paths to use /usr/lib64/ instead or /usr/lib
# Only used when "%%{_lib}" == "lib64"
# Not yet sent upstream.
Patch102: 00102-lib64.patch

# 00111 #
# Patch the Makefile.pre.in so that the generated Makefile doesn't try to build
# a libpythonMAJOR.MINOR.a
# See https://bugzilla.redhat.com/show_bug.cgi?id=556092
# Downstream only: not appropriate for upstream
Patch111: 00111-no-static-lib.patch

# 00132 #
# Add non-standard hooks to unittest for use in the "check" phase below, when
# running selftests within the build:
#   @unittest._skipInRpmBuild(reason)
# for tests that hang or fail intermittently within the build environment, and:
#   @unittest._expectedFailureInRpmBuild
# for tests that always fail within the build environment
#
# The hooks only take effect if WITHIN_PYTHON_RPM_BUILD is set in the
# environment, which we set manually in the appropriate portion of the "check"
# phase below (and which potentially other python-* rpms could set, to reuse
# these unittest hooks in their own "check" phases)
Patch132: 00132-add-rpmbuild-hooks-to-unittest.patch

# 00155 #
# Avoid allocating thunks in ctypes unless absolutely necessary, to avoid
# generating SELinux denials on "import ctypes" and "import uuid" when
# embedding Python within httpd
# See https://bugzilla.redhat.com/show_bug.cgi?id=814391
Patch155: 00155-avoid-ctypes-thunks.patch

# 00160 #
# Python 3.3 added os.SEEK_DATA and os.SEEK_HOLE, which may be present in the
# header files in the build chroot, but may not be supported in the running
# kernel, hence we disable this test in an rpm build.
# Adding these was upstream issue http://bugs.python.org/issue10142
# Not yet sent upstream
Patch160: 00160-disable-test_fs_holes-in-rpm-build.patch

# 00163 #
# Some tests within test_socket fail intermittently when run inside Koji;
# disable them using unittest._skipInRpmBuild
# Not yet sent upstream
Patch163: 00163-disable-parts-of-test_socket-in-rpm-build.patch

# 00170 #
# In debug builds, try to print repr() when a C-level assert fails in the
# garbage collector (typically indicating a reference-counting error
# somewhere else e.g in an extension module)
# The new macros/functions within gcmodule.c are hidden to avoid exposing
# them within the extension API.
# Sent upstream: http://bugs.python.org/issue9263
# See https://bugzilla.redhat.com/show_bug.cgi?id=614680
Patch170: 00170-gc-assertions.patch

# 00189 #
# Instead of bundled wheels, use our RPM packaged wheels from
# /usr/share/python3-wheels
Patch189: 00189-use-rpm-wheels.patch

# 00251
# Set values of prefix and exec_prefix in distutils install command
# to /usr/local if executable is /usr/bin/python* and RPM build
# is not detected to make pip and distutils install into separate location
# Fedora Change: https://fedoraproject.org/wiki/Changes/Making_sudo_pip_safe
Patch251: 00251-change-user-install-location.patch

# 00257 #
# Use the monotonic clock for threading.Condition.wait() as to not be affected by
# the system clock changes.
# This patch works around the issue.
# Implemented by backporting the respective python2 code:
# https://github.com/python/cpython/blob/v2.7.18/Lib/threading.py#L331
# along with our downstream patch for python2 fixing the same issue.
# Downstream only.
Patch257: 00257-threading-condition-wait.patch

# 00262 #
# Backport of PEP 538: Coercing the legacy C locale to a UTF-8 based locale
# https://www.python.org/dev/peps/pep-0538/
# Fedora Change: https://fedoraproject.org/wiki/Changes/python3_c.utf-8_locale
# Original proposal: https://bugzilla.redhat.com/show_bug.cgi?id=1404918
Patch262: 00262-pep538_coerce_legacy_c_locale.patch

# 00294 #
# Define TLS cipher suite on build time depending
# on the OpenSSL default cipher suite selection.
# Fixed upstream on CPython's 3.7 branch:
# https://bugs.python.org/issue31429
# See also: https://bugzilla.redhat.com/show_bug.cgi?id=1489816
Patch294: 00294-define-TLS-cipher-suite-on-build-time.patch

# 00316 #
# We remove the exe files from distutil's bdist_wininst
# So we mark the command as unsupported - and the tests are skipped
# Fixed upstream and backported from the 3.7 branch: https://bugs.python.org/issue10945
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1754040
Patch316: 00316-mark-bdist_wininst-unsupported.patch

# 00317 #
# Security fix for CVE-2019-5010: Fix segfault in ssl's cert parser
# https://bugzilla.redhat.com/show_bug.cgi?id=1666789
# Fixed upstream: https://bugs.python.org/issue35746
Patch317: 00317-CVE-2019-5010.patch

# 00318 #
# Various fixes for TLS 1.3 and OpenSSL 1.1.1
# https://bugzilla.redhat.com/show_bug.cgi?id=1639531

# test_ssl fixes for TLS 1.3 and OpenSSL 1.1.1
# https://bugs.python.org/issue32947#msg333990
# https://github.com/python/cpython/pull/11612

# Encrypt private key test files with AES256
# https://bugs.python.org/issue38271
# https://github.com/python/cpython/pull/16396

# Prefer PROTOCOL_TLS_CLIENT/SERVER (partial backport)
# https://bugs.python.org/issue31346
# https://github.com/python/cpython/pull/3058

# Enable TLS 1.3 in tests (partial backport)
# https://bugs.python.org/issue33618
# https://github.com/python/cpython/pull/7082

# OpenSSL 1.1.1-pre1 / TLS 1.3 fixes (partial backport)
# https://bugs.python.org/issue32947
# https://github.com/python/cpython/pull/5923
Patch318: 00318-fixes-for-tls-13.patch

# 00319 #
# Fix test_tarfile on ppc64
# https://bugzilla.redhat.com/show_bug.cgi?id=1639490
# https://bugs.python.org/issue35772
Patch319: 00319-test_tarfile_ppc64.patch

# 00320 #
# Security fix for CVE-2019-9636 and CVE-2019-10160: Information Disclosure due to urlsplit improper NFKC normalization
# Fixed upstream: https://bugs.python.org/issue36216 and https://bugs.python.org/issue36742
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1689318
Patch320: 00320-CVE-2019-9636-and-CVE-2019-10160.patch

# 00324 #
# Disallow control chars in http URLs
# Security fix for CVE-2019-9740 and CVE-2019-9947
# Fixed upstream: https://bugs.python.org/issue30458
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1704365
# and https://bugzilla.redhat.com/show_bug.cgi?id=1703531
Patch324: 00324-disallow-control-chars-in-http-urls.patch

# 00325 #
# Unnecessary URL scheme exists to allow local_file:// reading file  in urllib
# Security fix for CVE-2019-9948
# Fixed upstream: https://bugs.python.org/issue35907
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1714643
Patch325: 00325-CVE-2019-9948.patch

# 00326 #
# Don't set the post-handshake authentication verify flag on client side
# on TLS 1.3, as it also implicitly enables cert chain validation and an
# SSL/TLS connection will fail when verify mode is set to CERT_NONE.
# Fixed upstream: https://bugs.python.org/issue37428
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1725721
Patch326: 00326-do-not-set-PHA-verify-flag-on-client-side.patch

# 00327 #
# Enable TLS 1.3 post-handshake authentication in http.client for default
# context or if a cert_file is passed to HTTPSConnection
# Fixed upstream: https://bugs.python.org/issue37440
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1671353
Patch327: 00327-enable-tls-1.3-PHA-in-http.client.patch

# 00329 #
# Support OpenSSL FIPS mode
# - Fallback implementations md5, sha1, sha256, sha512 are removed in favor of OpenSSL wrappers
# - In FIPS mode, OpenSSL wrappers are always used in hashlib
# - add a new "usedforsecurity" keyword argument to the various digest
#   algorithms in hashlib so that you can whitelist a callsite with
#   "usedforsecurity=False"
#   The change has been implemented upstream since Python 3.9:
#   https://bugs.python.org/issue9216
# - OpenSSL wrappers for the hashes blake2{b512,s256},
#     sha3_{224,256,384,512}, shake_{128,256} are now exported from _hashlib
# - In FIPS mode, the blake2, sha3 and shake hashes use OpenSSL wrappers
#   and do not offer extended functionality (keys, tree hashing, custom digest size)
# - In FIPS mode, hmac.HMAC can only be instantiated with an OpenSSL wrapper
#   or an string with OpenSSL hash name as the "digestmod" argument.
#   The argument must be specified (instead of defaulting to ‘md5’).
#
# - Also while in FIPS mode, we utilize OpenSSL's DRBG and disable the
#   os.getrandom() function.
#
#   Upstream changes that have also been backported with this patch
#   to allow tests to pass on stricter environments:
#
#   Avoid MD5 or check for MD5 availablity
#   https://bugs.python.org/issue38270
#   https://github.com/python/cpython/pull/16393
#   https://github.com/python/cpython/pull/16437
#   https://github.com/python/cpython/pull/17446
#
#   add usedforsecurity to hashlib constructors (partial backport for fixing a uuid test)
#   https://github.com/python/cpython/pull/16044
# Resolves: rhbz#1731424
Patch329: 00329-fips.patch

# 00330 #
# Fix CVE-2018-20852: cookie domain check returning incorrect results
# Fixed upstream: https://bugs.python.org/issue35121
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1741553
Patch330: 00330-CVE-2018-20852.patch

# 00332 #
# Fix CVE-2019-16056: Don't parse email addresses containing
# multiple '@' characters.
# Fixed upstream: https://bugs.python.org/issue34155
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1750776
Patch332: 00332-CVE-2019-16056.patch

# 00333 #
# Reduce the number of tests run during the profile guided optimizations build,
# as running the whole test suite during profiling increases the build time
# substantially, with negligible performance gain.
# Fixed upstream and backported from the 3.8 branch:
# https://bugs.python.org/issue36044
# https://bugs.python.org/issue37667
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1749576
Patch333: 00333-reduce-pgo-tests.patch

# 00338 #
# Fix test_gdb for when compiling python with Link Time Optimizations
# Fixed upstream: https://bugs.python.org/issue38239
Patch338: 00338-fix-test_gdb-for-LTO.patch

# 00344 #
# Fix CVE-2019-16935: XSS vulnerability in the ocumentation XML-RPC server in server_title field
# Fixed upstream: https://bugs.python.org/issue38243
# Resolves: https://bugzilla.redhat.com/how_bug.cgi?id=1798001
Patch344: 00344-CVE-2019-16935.patch

# 00345 #
# Skip from test_site the test_startup_imports case if a path of sys.path
# contains a .pth file
# Fixed upstream: https://bugs.python.org/issue27807
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1814392
Patch345: 00345-fix-test_site-with-extra-pth-files.patch

# 00346 #
# Fix CVE-2020-8492: wrong backtracking in urllib.request.AbstractBasicAuthHandler allows for a ReDoS
# Fixed upstream: https://bugs.python.org/issue39503
# Resolves: https://bugzilla.redhat.com/show_bug.cgi?id=1810618
Patch346: 00346-CVE-2020-8492.patch

# 00351 #
# Avoid infinite loop when reading specially crafted TAR files using the tarfile module
# (CVE-2019-20907).
# See: https://bugs.python.org/issue39017
Patch351: 00351-avoid-infinite-loop-in-the-tarfile-module.patch

# 00352 # 5253c417a23b3658fa115d2c72fa54b20293a31c
# Resolve hash collisions for IPv4Interface and IPv6Interface
#
# CVE-2020-14422
# The hash() methods of classes IPv4Interface and IPv6Interface had issue
# of generating constant hash values of 32 and 128 respectively causing hash collisions.
# The fix uses the hash() function to generate hash values for the objects
# instead of XOR operation.
# Fixed upstream: https://bugs.python.org/issue41004
Patch352: 00352-resolve-hash-collisions-for-ipv4interface-and-ipv6interface.patch

# 00353 #
# Original names for architectures with different names downstream
#
# https://fedoraproject.org/wiki/Changes/Python_Upstream_Architecture_Names
#
# Pythons in RHEL/Fedora used different names for some architectures
# than upstream and other distros (for example ppc64 vs. powerpc64).
# This was patched in patch 274, now it is sedded if %%with legacy_archnames.
#
# That meant that an extension built with the default upstream settings
# (on other distro or as an manylinux wheel) could not been found by Python
# on RHEL/Fedora because it had a different suffix.
# This patch adds the legacy names to importlib so Python is able
# to import extensions with a legacy architecture name in its
# file name.
# It work both ways, so it support both %%with and %%without legacy_archnames.
#
# WARNING: This patch has no effect on Python built with bootstrap
# enabled because Python/importlib_external.h is not regenerated
# and therefore Python during bootstrap contains importlib from
# upstream without this feature. It's possible to include
# Python/importlib_external.h to this patch but it'd make rebasing
# a nightmare because it's basically a binary file.
Patch353: 00353-architecture-names-upstream-downstream.patch

# 00354 #
# Reject control chars in HTTP method in http.client to prevent
# HTTP header injection
# Fixed ustream: https://bugs.python.org/issue39603
Patch354: 00354-cve-2020-26116-http-request-method-crlf-injection-in-httplib.patch

# 00355 #
# No longer call eval() on content received via HTTP in the CJK codec tests
# Fixed upstream: https://bugs.python.org/issue41944
Patch355: 00355-CVE-2020-27619.patch

# 00356 #
# options -a and -k for pathfix.py used in %%py3_shebang_fix
# Upstream: https://github.com/python/cpython/commit/c71c54c62600fd721baed3c96709e3d6e9c33817
Patch356: 00356-k_and_a_options_for_pathfix.patch

# 00357 #
# CVE-2021-3177 stack-based buffer overflow in PyCArg_repr in _ctypes/callproc.c
# Upstream: https://bugs.python.org/issue42938
# Main BZ: https://bugzilla.redhat.com/show_bug.cgi?id=1918168
Patch357: 00357-CVE-2021-3177.patch

# 00359 #
# CVE-2021-23336 python: Web Cache Poisoning via urllib.parse.parse_qsl and
# urllib.parse.parse_qs by using a semicolon in query parameters
# Upstream: https://bugs.python.org/issue42967
# Main BZ: https://bugzilla.redhat.com/show_bug.cgi?id=1928904
Patch359: 00359-CVE-2021-23336.patch

# 00360 #
# CVE-2021-3426: information disclosure via pydoc
# Upstream: https://bugs.python.org/issue42988
# Main BZ: https://bugzilla.redhat.com/show_bug.cgi?id=1935913
Patch360: 00360-CVE-2021-3426.patch

# 00362 #
# The threading.enumerate() function now uses a reentrant lock to
# prevent a hang on reentrant call.
# Upstream: https://bugs.python.org/issue44422
# Main BZ: https://bugzilla.redhat.com/show_bug.cgi?id=1959459
Patch362: 00362-threading-enumerate-rlock.patch

# 00364 #
# Don't call PyThread_exit_thread() explicitly.
# Upstream: https://bugs.python.org/issue44434
# Main BZ: https://bugzilla.redhat.com/show_bug.cgi?id=1972293
Patch364: 00364-thread-exit.patch

# 00366 #
# CVE-2021-3733: Denial of service when identifying crafted invalid RFCs
# Upstream: https://bugs.python.org/issue43075
# Tracking bug: https://bugzilla.redhat.com/show_bug.cgi?id=1995234
Patch366: 00366-CVE-2021-3733.patch

# 00368 #
# CVE-2021-3737: client can enter an infinite loop on a 100 Continue response from the server
# Upstream: https://bugs.python.org/issue44022
# Tracking bug: https://bugzilla.redhat.com/show_bug.cgi?id=1995162
Patch368: 00368-CVE-2021-3737.patch

# 00369 #
# Change shouldRollover() methods of logging.handlers to only rollover regular files and not devices
# Upstream: https://bugs.python.org/issue45401
# Bugzilla: https://bugzilla.redhat.com/show_bug.cgi?id=2009200
Patch369: 00369-rollover-only-regular-files-in-logging-handlers.patch

# 00370 #
# Utilize the monotonic clock for the global interpreter lock instead of the real-time clock
# to avoid issues when the system time changes
# Upstream: https://bugs.python.org/issue12822
# Bugzilla: https://bugzilla.redhat.com/show_bug.cgi?id=2003758
Patch370: 00370-GIL-monotonic-clock.patch

# 00372 #
# CVE-2021-4189: ftplib should not use the host from the PASV response
# Upstream: https://bugs.python.org/issue43285
# Tracking bug: https://bugzilla.redhat.com/show_bug.cgi?id=2036020
Patch372: 00372-CVE-2021-4189.patch

# 00377 #
# CVE-2022-0391: urlparse does not sanitize URLs containing ASCII newline and tabs
#
# ASCII newline and tab characters are stripped from the URL.
#
# Upstream: https://bugs.python.org/issue43882
# Tracking bug: https://bugzilla.redhat.com/show_bug.cgi?id=2047376
Patch377: 00377-CVE-2022-0391.patch

# 00378 #
# Support expat 2.4.5
#
# Curly brackets were never allowed in namespace URIs
# according to RFC 3986, and so-called namespace-validating
# XML parsers have the right to reject them a invalid URIs.
#
# libexpat >=2.4.5 has become strcter in that regard due to
# related security issues; with ET.XML instantiating a
# namespace-aware parser under the hood, this test has no
# future in CPython.
#
# References:
# - https://datatracker.ietf.org/doc/html/rfc3968
# - https://www.w3.org/TR/xml-names/
#
# Also, test_minidom.py: Support Expat >=2.4.5
#
# The patch has diverged from upstream as the python test
# suite was relying on checking the expat version, whereas
# in RHEL fixes get backported instead of rebasing packages.
# 
# Upstream: https://bugs.python.org/issue46811
Patch378: 00378-support-expat-2-4-5.patch

# 00382 #
# CVE-2015-20107
#
# Make mailcap refuse to match unsafe filenames/types/params (GH-91993)
#
# Upstream: https://github.com/python/cpython/issues/68966
#
# Tracker bug: https://bugzilla.redhat.com/show_bug.cgi?id=2075390
Patch382: 00382-cve-2015-20107.patch

# 00386 #
# CVE-2021-28861
#
# Fix an open redirection vulnerability in the `http.server` module when
# an URI path starts with `//` that could produce a 301 Location header
# with a misleading target.  Vulnerability discovered, and logic fix
# proposed, by Hamza Avvan (@hamzaavvan).
#
# Test and comments authored by Gregory P. Smith [Google].
#
# Upstream: https://github.com/python/cpython/pull/93879
# Tracking bugzilla: https://bugzilla.redhat.com/show_bug.cgi?id=2120642
Patch386: 00386-cve-2021-28861.patch

# 00387 #
# CVE-2020-10735: Prevent DoS by very large int()
#
# gh-95778: CVE-2020-10735: Prevent DoS by very large int() (GH-96504)
#
# Converting between `int` and `str` in bases other than 2
# (binary), 4, 8 (octal), 16 (hexadecimal), or 32 such as base 10 (decimal) now
# raises a `ValueError` if the number of digits in string form is above a
# limit to avoid potential denial of service attacks due to the algorithmic
# complexity. This is a mitigation for CVE-2020-10735
# (https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2020-10735).
#
# This new limit can be configured or disabled by environment variable, command
# line flag, or :mod:`sys` APIs. See the `Integer String Conversion Length
# Limitation` documentation.  The default limit is 4300
# digits in string form.
#
# Patch by Gregory P. Smith [Google] and Christian Heimes [Red Hat] with feedback
# from Victor Stinner, Thomas Wouters, Steve Dower, Ned Deily, and Mark Dickinson.
#
# Notes on the backport to Python 3.6 in RHEL:
#
# * Use "Python 3.6.8-48" version in the documentation, whereas this
#   version will never be released
# * Only add _Py_global_config_int_max_str_digits global variable:
#   Python 3.6 doesn't have PyConfig API (PEP 597) nor _PyRuntime.
# * sys.flags.int_max_str_digits cannot be -1 on Python 3.6: it is
#   set to the default limit. Adapt test_int_max_str_digits() for that.
# * Declare _PY_LONG_DEFAULT_MAX_STR_DIGITS and
#   _PY_LONG_MAX_STR_DIGITS_THRESHOLD macros in longobject.h but only
#   if the Py_BUILD_CORE macro is defined.
# * Declare _Py_global_config_int_max_str_digits in pydebug.h.
#
#
# gh-95778: Mention sys.set_int_max_str_digits() in error message (#96874)
#
# When ValueError is raised if an integer is larger than the limit,
# mention sys.set_int_max_str_digits() in the error message.
#
#
# gh-96848: Fix -X int_max_str_digits option parsing (#96988)
#
# Fix command line parsing: reject "-X int_max_str_digits" option with
# no value (invalid) when the PYTHONINTMAXSTRDIGITS environment
# variable is set to a valid limit.
Patch387: 00387-cve-2020-10735-prevent-dos-by-very-large-int.patch

# 00394 #
# CVE-2022-45061: CPU denial of service via inefficient IDNA decoder
#
# gh-98433: Fix quadratic time idna decoding.
#
# There was an unnecessary quadratic loop in idna decoding. This restores
# the behavior to linear.
Patch394: 00394-cve-2022-45061-cpu-denial-of-service-via-inefficient-idna-decoder.patch

# 00397 #
# Add filters for tarfile extraction (CVE-2007-4559, PEP-706)
# The first patches in the file backport the upstream fix:
# - https://github.com/python/cpython/pull/104583
#   (see the linked issue for merged backports)
# Next-to-last patch fixes determination of symlink targets, which were treated
#   as relative to the root of the archive,
#   rather than the directory containing the symlink.
#   Not yet upstream as of this writing.
# The last patch is Red Hat configuration, see KB for documentation:
# - https://access.redhat.com/articles/7004769
Patch397: 00397-tarfile-filter.patch

# 00399 #
# CVE-2023-24329
#
# gh-102153: Start stripping C0 control and space chars in `urlsplit` (GH-102508)
#
# `urllib.parse.urlsplit` has already been respecting the WHATWG spec a bit GH-25595.
#
# This adds more sanitizing to respect the "Remove any leading C0 control or space from input" [rule](https://url.spec.whatwg.org/GH-url-parsing:~:text=Remove%%20any%%20leading%%20and%%20trailing%%20C0%%20control%%20or%%20space%%20from%%20input.) in response to [CVE-2023-24329](https://nvd.nist.gov/vuln/detail/CVE-2023-24329).
#
# Backported from Python 3.12
Patch399: 00399-cve-2023-24329.patch

# 00404 #
# CVE-2023-40217
#
# Security fix for CVE-2023-40217: Bypass TLS handshake on closed sockets
# Resolved upstream: https://github.com/python/cpython/issues/108310
# Fixups added on top:
# https://github.com/python/cpython/pull/108352
# https://github.com/python/cpython/pull/108408
#
# Backported from Python 3.8
Patch404: 00404-cve-2023-40217.patch
Patch405: 5000-add-to-supported-dists.patch

# (New patches go here ^^^)
#
# When adding new patches to "python" and "python3" in Fedora, EL, etc.,
# please try to keep the patch numbers in-sync between all specfiles.
#
# More information, and a patch number catalog, is at:
#
#     https://fedoraproject.org/wiki/SIGs/Python/PythonPatches


# ==========================================
# Descriptions, and metadata for subpackages
# ==========================================

%package -n platform-python
Summary: Internal interpreter of the Python programming language

Conflicts: python3 < 3.6.6-13

# Packages with Python modules in standard locations automatically
# depend on python(abi). Provide that here.
Provides: python(abi) = %{pybasever}

Requires: %{name}-libs%{?_isa} = %{version}-%{release}

%if %{with rpmwheels}

# RHEL8 was forked from F28 and thus required python3-setuptools here
# for the rewheel module to work. We've since backported the use of RPM
# prepared wheels from F29+ into RHEL8, and thus this dependency isn't
# strictly needed.
# However, it is possible, that some packages in BaseOS actually depend on
# setuptools without declaring the dependency in their spec file. Thus
# we're keeping this dependency here to avoid the possibility of breaking
# them.
Requires: platform-python-setuptools
# For python3-pip the Requires has been reduced to Recommends, as there are
# generally less packages that depend on pip than packages that depend on
# setuptools at runtime, and thus there's less chance of breakage.
# (rhbz#1756217).
Recommends: platform-python-pip

Requires: python3-setuptools-wheel
Requires: python3-pip-wheel
%endif

# Require alternatives version that implements the --keep-foreign flag
Requires: alternatives >= 1.19.1-1
Requires(post):   alternatives >= 1.19.1-1
Requires(postun): alternatives >= 1.19.1-1

# This prevents ALL subpackages built from this spec to require
# /usr/bin/python3*. Granularity per subpackage is impossible.
# It's intended for the libs package not to drag in the interpreter, see
# https://bugzilla.redhat.com/show_bug.cgi?id=1547131
# All others require %%{name} anyway.
%global __requires_exclude ^/usr/bin/python3


# The description is the same for the SRPM and the main `platform-python` subpackage:
%description
This is the internal interpreter of the Python language for the system.
To use Python yourself, please install one of the available Python 3 packages,
for example python36.


# The description is the same for the SRPM and the main `platform-python` subpackage:
%description -n platform-python
This is the internal interpreter of the Python language for the system.
To use Python yourself, please install one of the available Python 3 packages,
for example python36.


%package libs
Summary: Python runtime libraries

# The "enum" module is included in the standard library.
# Provide an upgrade path from the external library.
Provides: python3-enum34 = 1.0.4-5%{?dist}
Obsoletes: python3-enum34 < 1.0.4-5%{?dist}

# Python 3 built with glibc >= 2.24.90-26 needs to require it
# See https://bugzilla.redhat.com/show_bug.cgi?id=1410644
Requires: glibc%{?_isa} >= 2.24.90-26

Requires: chkconfig

%if %{with gdbm}
# When built with this (as guarded by the BuildRequires above), require it
Requires: gdbm%{?_isa} >= 1:1.13
%endif

%if %{with rpmwheels}
Requires: python3-setuptools-wheel
Requires: python3-pip-wheel
%else
Provides: bundled(python3-pip) = 18.1
Provides: bundled(python3-setuptools) = 40.6.2
%endif

# There are files in the standard library that have python shebang.
# We've filtered the automatic requirement out so libs are installable without
# the main package. This however makes it pulled in by default.
# See https://bugzilla.redhat.com/show_bug.cgi?id=1547131
Recommends: platform-python%{?_isa} = %{version}-%{release}

%description libs
This package contains runtime libraries for use by Python:
- the majority of the Python standard library
- a dynamically linked library for use by applications that embed Python as
  a scripting language, and by the main "python3" executable


# The contents of this package were moved into the `platform-python-devel` subpackage.
# See a comment above the definition of that subpackage for details.
%package devel
Summary: Libraries and header files needed for Python development
Requires: platform-python-devel%{?_isa} = %{version}-%{release}
Requires: platform-python = %{version}-%{release}
Requires: python36-devel

%description devel
This package contains the header files and configuration needed to compile
Python extension modules (typically written in C or C++), to embed Python
into other programs, and to make binary distributions for Python libraries.

It also contains the necessary macros to build RPM packages with Python modules
and 2to3 tool, an automatic source converter from Python 2.X.

It also makes the "python3" and "python3-config" commands available
for compatibility with some build systems.
When building packages, prefer requiring platform-python-devel and using
the %%{__python3} macro instead, if possible.



# The `platform-python-devel` (previously python3-libs-devel)
# subpackage was created because the `python3-devel` subpackage needs
# to pull into the buildroot the /usr/bin/python3{,-config} symlinks (for old
# buildsystems that are hard to switch to platform-python). But these symlinks
# cannot be shipped in RHEL8 to customers. Therefore we'll ship only
# `platform-python-devel` and have the `python3-devel` package require it in
# the buildroot, as well as pull in the symlinks.
%package -n platform-python-devel
Summary: Libraries and header files needed for Python development
Provides: %{name}-libs-devel = %{version}-%{release}
Provides: %{name}-libs-devel%{?_isa} = %{version}-%{release}
Obsoletes: %{name}-libs-devel < 3.6.6-12
Requires: platform-python = %{version}-%{release}
Requires: %{name}-libs%{?_isa} = %{version}-%{release}
BuildRequires: python-rpm-macros
Requires: python-rpm-macros
Requires: python3-rpm-macros
Requires: python3-rpm-generators

# This is not "API" (packages that need setuptools should still BuildRequire it)
# However some packages apparently can build both with and without setuptools
# producing egg-info as file or directory (depending on setuptools presence).
# Directory-to-file updates are problematic in RPM, so we ensure setuptools is
# installed when -devel is required.
# See https://bugzilla.redhat.com/show_bug.cgi?id=1623914
# See https://fedoraproject.org/wiki/Packaging:Directory_Replacement
Requires: platform-python-setuptools

Provides: %{name}-2to3 = %{version}-%{release}
Provides: 2to3 = %{version}-%{release}

Conflicts: platform-python < %{version}-%{release}
Conflicts: python3 < 3.6.6-9

%description -n platform-python-devel
This package contains the header files and configuration needed to compile
Python extension modules (typically written in C or C++), to embed Python
into other programs, and to make binary distributions for Python libraries.

It also contains the necessary macros to build RPM packages with Python modules
and 2to3 tool, an automatic source converter from Python 2.X.


%package idle
Summary: A basic graphical development environment for Python
Requires: platform-python = %{version}-%{release}
Requires: %{name}-tkinter = %{version}-%{release}

Provides: idle3 = %{version}-%{release}

Provides: %{name}-tools = %{version}-%{release}
Provides: %{name}-tools%{?_isa} = %{version}-%{release}
Obsoletes: %{name}-tools < %{version}-%{release}


# Require alternatives version that implements the --keep-foreign flag
Requires(postun): alternatives >= 1.19.1-1
# python36 installs the alternatives master symlink to which we attach a slave
Requires: python36
Requires(post): python36
Requires(postun): python36

%description idle
IDLE is Python’s Integrated Development and Learning Environment.

IDLE has the following features: Python shell window (interactive
interpreter) with colorizing of code input, output, and error messages;
multi-window text editor with multiple undo, Python colorizing,
smart indent, call tips, auto completion, and other features;
search within any window, replace within editor windows, and
search through multiple files (grep); debugger with persistent
breakpoints, stepping, and viewing of global and local namespaces;
configuration, browsers, and other dialogs.


%package tkinter
Summary: A GUI toolkit for Python
Requires: platform-python = %{version}-%{release}
Requires: %{name}-libs%{?_isa} = %{version}-%{release}

%description tkinter
The Tkinter (Tk interface) library is a graphical user interface toolkit for
the Python programming language.


%package test
Summary: The self-test suite for the main python3 package
Requires: platform-python = %{version}-%{release}
Requires: %{name}-libs%{?_isa} = %{version}-%{release}

%description test
The self-test suite for the Python interpreter.

This is only useful to test Python itself. For testing general Python code,
you should use the unittest module from %{name}-libs, or a library such as
%{name}-pytest or %{name}-nose.


%if %{with debug_build}
%package -n platform-python-debug
Conflicts: python3-debug < 3.6.6-13
Summary: Debug version of the Python runtime

# The debug build is an all-in-one package version of the regular build, and
# shares the same .py/.pyc files and directories as the regular build. Hence
# we depend on all of the subpackages of the regular build:
Requires: platform-python%{?_isa} = %{version}-%{release}
Requires: %{name}-libs%{?_isa} = %{version}-%{release}
Requires: platform-python-devel%{?_isa} = %{version}-%{release}
Requires: %{name}-test%{?_isa} = %{version}-%{release}
Requires: %{name}-tkinter%{?_isa} = %{version}-%{release}
Requires: %{name}-idle%{?_isa} = %{version}-%{release}

%description -n platform-python-debug
python3-debug provides a version of the Python runtime with numerous debugging
features enabled, aimed at advanced Python users such as developers of Python
extension modules.

This version uses more memory and will be slower than the regular Python build,
but is useful for tracking down reference-counting issues and other bugs.

The bytecode format is unchanged, so that .pyc files are compatible between
this and the standard version of Python, but the debugging features mean that
C/C++ extension modules are ABI-incompatible and must be built for each version
separately.

The debug build shares installation directories with the standard Python
runtime, so that .py and .pyc files can be shared.
Compiled extension modules use a special ABI flag ("d") in the filename,
so extensions for both versions can co-exist in the same directory.
%endif # with debug_build


# ======================================================
# The prep phase of the build:
# ======================================================

%prep
%setup -q -n Python-%{version}%{?prerel}

# Remove bundled libraries to ensure that we're using the system copy.
rm -r Modules/expat
rm -r Modules/zlib

#
# Apply patches:
#
%patch1 -p1

%if "%{_lib}" == "lib64"
%patch102 -p1
%endif
%patch111 -p1
%patch132 -p1
%patch155 -p1
%patch160 -p1
%patch163 -p1
%patch170 -p1

%if %{with rpmwheels}
%patch189 -p1
rm Lib/ensurepip/_bundled/*.whl
%endif

%patch251 -p1
%patch257 -p1
%patch262 -p1
%patch294 -p1
%patch316 -p1
%patch317 -p1
%patch318 -p1
%patch319 -p1
%patch320 -p1
%patch324 -p1
%patch325 -p1
%patch326 -p1
%patch327 -p1
%patch329 -p1
%patch330 -p1
%patch332 -p1
%patch333 -p1
%patch338 -p1
%patch344 -p1
%patch345 -p1
%patch346 -p1

# Patch 351 adds binary file for testing. We need to apply it using Git.
git apply %{PATCH351}

%patch352 -p1
%patch353 -p1
%patch354 -p1
%patch355 -p1
%patch356 -p1
%patch357 -p1
%patch359 -p1
%patch360 -p1
%patch362 -p1
%patch364 -p1
%patch366 -p1
%patch368 -p1
%patch369 -p1
%patch370 -p1
%patch372 -p1
%patch377 -p1
%patch378 -p1
%patch382 -p1
%patch386 -p1
%patch387 -p1
%patch394 -p1
%patch397 -p1
%patch399 -p1
%patch404 -p1

# Remove files that should be generated by the build
# (This is after patching, so that we can use patches directly from upstream)
rm configure pyconfig.h.in

# When we use the legacy arch names, we need to change them in configure.ac
%if %{with legacy_archnames}
sed -i configure.ac \
    -e 's/\b%{platform_triplet_upstream}\b/%{platform_triplet_legacy}/'
%endif


# ======================================================
# Configuring and building the code:
# ======================================================
%patch405 -p1

%build

# Regenerate the configure script and pyconfig.h.in
autoconf
autoheader

# Remember the current directory (which has sources and the configure script),
# so we can refer to it after we "cd" elsewhere.
topdir=$(pwd)

# Get proper option names from bconds
%if %{with computed_gotos}
%global computed_gotos_flag yes
%else
%global computed_gotos_flag no
%endif

%if %{with optimizations}
%global optimizations_flag "--enable-optimizations"
%else
%global optimizations_flag "--disable-optimizations"
%endif

# Set common compiler/linker flags
# We utilize the %%extension_...flags macros here so users building C/C++
# extensions with our python won't get all the compiler/linker flags used
# in RHEL RPMs.
# Standard library built here will still use the %%build_...flags,
# RHEL packages utilizing %%py3_build will use them as well
# https://fedoraproject.org/wiki/Changes/Python_Extension_Flags
export CFLAGS="%{extension_cflags} -D_GNU_SOURCE -fPIC -fwrapv"
export CFLAGS_NODIST="%{build_cflags} -D_GNU_SOURCE -fPIC -fwrapv -fno-semantic-interposition"
export CXXFLAGS="%{extension_cxxflags} -D_GNU_SOURCE -fPIC -fwrapv"
export CPPFLAGS="$(pkg-config --cflags-only-I libffi)"
export OPT="%{extension_cflags} -D_GNU_SOURCE -fPIC -fwrapv"
export LINKCC="gcc"
export CFLAGS="$CFLAGS $(pkg-config --cflags openssl)"
export LDFLAGS="%{extension_ldflags} -g $(pkg-config --libs-only-L openssl)"
export LDFLAGS_NODIST="%{build_ldflags} -fno-semantic-interposition -g $(pkg-config --libs-only-L openssl)"

# We can build several different configurations of Python: regular and debug.
# Define a common function that does one build:
BuildPython() {
  ConfName=$1
  ExtraConfigArgs=$2
  MoreCFlags=$3

  # Each build is done in its own directory
  ConfDir=build/$ConfName
  echo STARTING: BUILD OF PYTHON FOR CONFIGURATION: $ConfName
  mkdir -p $ConfDir
  pushd $ConfDir

  # Normally, %%configure looks for the "configure" script in the current
  # directory.
  # Since we changed directories, we need to tell %%configure where to look.
  %global _configure $topdir/configure

%configure \
  --enable-ipv6 \
  --enable-shared \
  --with-computed-gotos=%{computed_gotos_flag} \
  --with-dbmliborder=gdbm:ndbm:bdb \
  --with-system-expat \
  --with-system-ffi \
  --enable-loadable-sqlite-extensions \
  --with-dtrace \
  --with-lto \
  --with-ssl-default-suites=openssl \
%if %{with valgrind}
  --with-valgrind \
%endif
  $ExtraConfigArgs \
  %{nil}

  # Regenerate generated importlib frozen modules (see patch 353)
  %make_build CFLAGS_NODIST="$CFLAGS_NODIST $MoreCFlags" regen-importlib

  # Invoke the build
  %make_build CFLAGS_NODIST="$CFLAGS_NODIST $MoreCFlags"

  popd
  echo FINISHED: BUILD OF PYTHON FOR CONFIGURATION: $ConfName
}

# Call the above to build each configuration.

%if %{with debug_build}
BuildPython debug \
  "--without-ensurepip --with-pydebug" \
  "-Og"
%endif # with debug_build

BuildPython optimized \
  "--without-ensurepip %{optimizations_flag}" \
  ""

# ======================================================
# Installing the built code:
# ======================================================

%install

# As in %%build, remember the current directory
topdir=$(pwd)

# We install a collection of hooks for gdb that make it easier to debug
# executables linked against libpython3* (such as /usr/bin/python3 itself)
#
# These hooks are implemented in Python itself (though they are for the version
# of python that gdb is linked with)
#
# gdb-archer looks for them in the same path as the ELF file or its .debug
# file, with a -gdb.py suffix.
# We put them next to the debug file, because ldconfig would complain if
# it found non-library files directly in /usr/lib/
# (see https://bugzilla.redhat.com/show_bug.cgi?id=562980)
#
# We'll put these files in the debuginfo package by installing them to e.g.:
#  /usr/lib/debug/usr/lib/libpython3.2.so.1.0.debug-gdb.py
# (note that the debug path is /usr/lib/debug for both 32/64 bit)
#
# See https://fedoraproject.org/wiki/Features/EasierPythonDebugging for more
# information

%if %{with gdb_hooks}
DirHoldingGdbPy=%{_prefix}/lib/debug/%{_libdir}
mkdir -p %{buildroot}$DirHoldingGdbPy
%endif # with gdb_hooks

# Multilib support for pyconfig.h
# 32- and 64-bit versions of pyconfig.h are different. For multilib support
# (making it possible to install 32- and 64-bit versions simultaneously),
# we need to install them under different filenames, and to make the common
# "pyconfig.h" include the right file based on architecture.
# See https://bugzilla.redhat.com/show_bug.cgi?id=192747
# Filanames are defined here:
%global _pyconfig32_h pyconfig-32.h
%global _pyconfig64_h pyconfig-64.h
%global _pyconfig_h pyconfig-%{wordsize}.h


# Use a common function to do an install for all our configurations:
InstallPython() {

  ConfName=$1
  PyInstSoName=$2
  MoreCFlags=$3
  LDVersion=$4

  # Switch to the directory with this configuration's built files
  ConfDir=build/$ConfName
  echo STARTING: INSTALL OF PYTHON FOR CONFIGURATION: $ConfName
  mkdir -p $ConfDir
  pushd $ConfDir

  make \
    DESTDIR=%{buildroot} \
    INSTALL="install -p" \
    EXTRA_CFLAGS="$MoreCFlags" \
    install

  popd

%if %{with gdb_hooks}
  # See comment on $DirHoldingGdbPy above
  PathOfGdbPy=$DirHoldingGdbPy/$PyInstSoName-%{version}-%{release}.%{_arch}.debug-gdb.py
  cp Tools/gdb/libpython.py %{buildroot}$PathOfGdbPy
%endif # with gdb_hooks

  # Rename the -devel script that differs on different arches to arch specific name
  mv %{buildroot}%{_bindir}/python${LDVersion}-{,`uname -m`-}config
  echo -e '#!/bin/sh\nexec %{_libexecdir}/platform-python'${LDVersion}'-`uname -m`-config "$@"' > \
    %{buildroot}%{_bindir}/python${LDVersion}-config
  echo '[ $? -eq 127 ] && echo "Could not find %{_libexecdir}/platform-python'${LDVersion}'-`uname -m`-config. Look around to see available arches." >&2' >> \
    %{buildroot}%{_bindir}/python${LDVersion}-config
    chmod +x %{buildroot}%{_bindir}/python${LDVersion}-config

  # Platform Python: Move the python*-config to libexec
  mkdir -p %{buildroot}%{_libexecdir}
  mv %{buildroot}%{_bindir}/python${LDVersion}-config %{buildroot}%{_libexecdir}/platform-python${LDVersion}-config
  ln -s %{_libexecdir}/platform-python${LDVersion}-config %{buildroot}%{_bindir}/python${LDVersion}-config
  mv %{buildroot}%{_bindir}/python${LDVersion}-`uname -m`-config %{buildroot}%{_libexecdir}/platform-python${LDVersion}-`uname -m`-config
  ln -s %{_libexecdir}/platform-python${LDVersion}-`uname -m`-config %{buildroot}%{_bindir}/python${LDVersion}-`uname -m`-config

  # Platform Python: Move optimized and debug executables
  mv %{buildroot}%{_bindir}/python${LDVersion} %{buildroot}%{_libexecdir}/platform-python${LDVersion}
  ln -s %{_libexecdir}/platform-python${LDVersion} %{buildroot}%{_bindir}/python${LDVersion}

  # Make python3-devel multilib-ready
  mv %{buildroot}%{_includedir}/python${LDVersion}/pyconfig.h \
     %{buildroot}%{_includedir}/python${LDVersion}/%{_pyconfig_h}
  cat > %{buildroot}%{_includedir}/python${LDVersion}/pyconfig.h << EOF
#include <bits/wordsize.h>

#if __WORDSIZE == 32
#include "%{_pyconfig32_h}"
#elif __WORDSIZE == 64
#include "%{_pyconfig64_h}"
#else
#error "Unknown word size"
#endif
EOF

  echo FINISHED: INSTALL OF PYTHON FOR CONFIGURATION: $ConfName
}

# Install the "debug" build first; any common files will be overridden with
# later builds
%if %{with debug_build}
InstallPython debug \
  %{py_INSTSONAME_debug} \
  -O0 \
  %{LDVERSION_debug}
%endif # with debug_build

# Now the optimized build:
InstallPython optimized \
  %{py_INSTSONAME_optimized} \
  "" \
  %{LDVERSION_optimized}

# Install directories for additional packages
install -d -m 0755 %{buildroot}%{pylibdir}/site-packages/__pycache__
%if "%{_lib}" == "lib64"
# The 64-bit version needs to create "site-packages" in /usr/lib/ (for
# pure-Python modules) as well as in /usr/lib64/ (for packages with extension
# modules).
# Note that rpmlint will complain about hardcoded library path;
# this is intentional.
install -d -m 0755 %{buildroot}%{_prefix}/lib/python%{pybasever}/site-packages/__pycache__
%endif

# add idle3 to menu
install -D -m 0644 Lib/idlelib/Icons/idle_16.png %{buildroot}%{_datadir}/icons/hicolor/16x16/apps/idle3.png
install -D -m 0644 Lib/idlelib/Icons/idle_32.png %{buildroot}%{_datadir}/icons/hicolor/32x32/apps/idle3.png
install -D -m 0644 Lib/idlelib/Icons/idle_48.png %{buildroot}%{_datadir}/icons/hicolor/48x48/apps/idle3.png
desktop-file-install --dir=%{buildroot}%{_datadir}/applications %{SOURCE10}

# Install and validate appdata file
mkdir -p %{buildroot}%{_metainfodir}
cp -a %{SOURCE11} %{buildroot}%{_metainfodir}
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/idle3.appdata.xml

# Make sure distutils looks at the right pyconfig.h file
# See https://bugzilla.redhat.com/show_bug.cgi?id=201434
# Similar for sysconfig: sysconfig.get_config_h_filename tries to locate
# pyconfig.h so it can be parsed, and needs to do this at runtime in site.py
# when python starts up (see https://bugzilla.redhat.com/show_bug.cgi?id=653058)
#
# Split this out so it goes directly to the pyconfig-32.h/pyconfig-64.h
# variants:
sed -i -e "s/'pyconfig.h'/'%{_pyconfig_h}'/" \
  %{buildroot}%{pylibdir}/distutils/sysconfig.py \
  %{buildroot}%{pylibdir}/sysconfig.py

# Install pathfix.py to bindir
# See https://github.com/fedora-python/python-rpm-porting/issues/24
cp -p Tools/scripts/pathfix.py %{buildroot}%{_bindir}/

# Switch all shebangs to refer to the specific Python version.
# This currently only covers files matching ^[a-zA-Z0-9_]+\.py$,
# so handle files named using other naming scheme separately.
# - Files in /usr/bin/ (without .py) are listed manually
LD_LIBRARY_PATH=./build/optimized ./build/optimized/python \
  Tools/scripts/pathfix.py \
  -i "%{_libexecdir}/platform-python" -pn \
  %{buildroot} \
  %{?with_gdb_hooks:%{buildroot}$DirHoldingGdbPy/*.py} \
  %{buildroot}%{_bindir}/{idle,pydoc,pyvenv-,2to3-}%{pybasever}

# The python-config.py files need to be shebanged with the given LDVERSION'ed
# executable
for LDVersion in %{LDVERSION_optimized} %{LDVERSION_debug}
do
  LD_LIBRARY_PATH=./build/optimized ./build/optimized/python \
    Tools/scripts/pathfix.py \
    -i "%{_libexecdir}/platform-python${LDVersion}" -pn \
    %{buildroot}%{pylibdir}/config-${LDVersion}-%{platform_triplet}/python-config.py
done

# Remove tests for python3-tools which was removed in
# https://bugzilla.redhat.com/show_bug.cgi?id=1312030
rm -rf %{buildroot}%{pylibdir}/test/test_tools

# Remove shebang lines from .py files that aren't executable, and
# remove executability from .py files that don't have a shebang line:
find %{buildroot} -name \*.py \
  \( \( \! -perm /u+x,g+x,o+x -exec sed -e '/^#!/Q 0' -e 'Q 1' {} \; \
  -print -exec sed -i '1d' {} \; \) -o \( \
  -perm /u+x,g+x,o+x ! -exec grep -m 1 -q '^#!' {} \; \
  -exec chmod a-x {} \; \) \)

# Get rid of DOS batch files:
find %{buildroot} -name \*.bat -exec rm {} \;

# Get rid of backup files:
find %{buildroot}/ -name "*~" -exec rm -f {} \;
find . -name "*~" -exec rm -f {} \;

# Get rid of a stray copy of the license:
rm %{buildroot}%{pylibdir}/LICENSE.txt

# Do bytecompilation with the newly installed interpreter.
# This is similar to the script in macros.pybytecompile
# compile *.pyc
find %{buildroot} -type f -a -name "*.py" -print0 | \
    LD_LIBRARY_PATH="%{buildroot}%{dynload_dir}/:%{buildroot}%{_libdir}" \
    PYTHONPATH="%{buildroot}%{_libdir}/python%{pybasever} %{buildroot}%{_libdir}/python%{pybasever}/site-packages" \
    xargs -0 %{buildroot}%{_bindir}/python%{pybasever} -O -c 'import py_compile, sys; [py_compile.compile(f, dfile=f.partition("%{buildroot}")[2], optimize=opt) for opt in range(3) for f in sys.argv[1:]]' || :

# Since we have pathfix.py in bindir, this is created, but we don't want it
rm -rf %{buildroot}%{_bindir}/__pycache__

# Fixup permissions for shared libraries from non-standard 555 to standard 755:
find %{buildroot} -perm 555 -exec chmod 755 {} \;

# Install macros for rpm:
mkdir -p %{buildroot}/%{_rpmconfigdir}/macros.d/

# Create "/usr/bin/python3-debug" (and /usr/libexec/platform-python-debug),
# a symlink to the python3 debug binary, to
# avoid the user having to know the precise version and ABI flags.
# See e.g. https://bugzilla.redhat.com/show_bug.cgi?id=676748
%if %{with debug_build}
ln -s \
  %{_bindir}/python%{LDVERSION_debug} \
  %{buildroot}%{_bindir}/python3-debug
ln -s \
  %{_libexecdir}/platform-python%{LDVERSION_debug} \
  %{buildroot}%{_libexecdir}/platform-python-debug
%endif


# Platform Python: Move the executable to libexec & provide a symlink from bindir
# (this symlink will be moved to the python36 module)
mkdir -p %{buildroot}%{_libexecdir}
mv %{buildroot}%{_bindir}/python%{pybasever} %{buildroot}%{_libexecdir}/platform-python%{pybasever}
ln -s %{_libexecdir}/platform-python%{pybasever} %{buildroot}%{_bindir}/python%{pybasever}
ln -s ./platform-python%{pybasever} %{buildroot}%{_libexecdir}/platform-python

# Platform Python: Add symlink from platform-python-config
ln -s ./platform-python%{LDVERSION_optimized}-config %{buildroot}%{_libexecdir}/platform-python%{pybasever}-config
ln -s ./platform-python%{pybasever}-config %{buildroot}%{_libexecdir}/platform-python-config

# Remove symlinks <name>3 > <name>3.6 for pydoc, idle, manpage
rm %{buildroot}%{_bindir}/pydoc3
rm %{buildroot}%{_bindir}/idle3
rm %{buildroot}%{_mandir}/man1/python3.1

# Install the unversioned-python script and its man page
install -m 755 %{SOURCE12} %{buildroot}%{_libexecdir}/no-python
install -m 644 %{SOURCE13} %{buildroot}%{_mandir}/man1/unversioned-python.1
# Touch the files that are controlled by `alternatives` so we can declare them
# as ghosts in the files section
touch %{buildroot}%{_bindir}/unversioned-python
touch %{buildroot}%{_bindir}/idle3
touch %{buildroot}%{_mandir}/man1/python.1.gz

# Strip the LTO bytecode from python.o
# Based on the fedora brp-strip-lto scriptlet
# https://src.fedoraproject.org/rpms/redhat-rpm-config/blob/9dd5528cf9805ebfe31cff04fe7828ad06a6023f/f/brp-strip-lto
find %{buildroot} -type f -name 'python.o' -print0 | xargs -0 \
bash -c "strip -p -R .gnu.lto_* -R .gnu.debuglto_* -N __gnu_lto_v1 \"\$@\"" ARG0

# ======================================================
# Checks for packaging issues
# ======================================================

%check
# first of all, check timestamps of bytecode files
find %{buildroot} -type f -a -name "*.py" -print0 | \
    LD_LIBRARY_PATH="%{buildroot}%{dynload_dir}/:%{buildroot}%{_libdir}" \
    PYTHONPATH="%{buildroot}%{_libdir}/python%{pybasever} %{buildroot}%{_libdir}/python%{pybasever}/site-packages" \
    xargs -0 %{buildroot}%{_libexecdir}/platform-python %{SOURCE8}

# Ensure that the curses module was linked against libncursesw.so, rather than
# libncurses.so
# See https://bugzilla.redhat.com/show_bug.cgi?id=539917
ldd %{buildroot}/%{dynload_dir}/_curses*.so \
    | grep curses \
    | grep libncurses.so && (echo "_curses.so linked against libncurses.so" ; exit 1)

# Ensure that the debug modules are linked against the debug libpython, and
# likewise for the optimized modules and libpython:
for Module in %{buildroot}/%{dynload_dir}/*.so ; do
    case $Module in
    *.%{SOABI_debug})
        ldd $Module | grep %{py_INSTSONAME_optimized} &&
            (echo Debug module $Module linked against optimized %{py_INSTSONAME_optimized} ; exit 1)

        ;;
    *.%{SOABI_optimized})
        ldd $Module | grep %{py_INSTSONAME_debug} &&
            (echo Optimized module $Module linked against debug %{py_INSTSONAME_debug} ; exit 1)
        ;;
    esac
done

# ======================================================
# Running the upstream test suite
# ======================================================

topdir=$(pwd)
CheckPython() {
  ConfName=$1
  ConfDir=$(pwd)/build/$ConfName

  export OPENSSL_CONF=/non-existing-file

  echo STARTING: CHECKING OF PYTHON FOR CONFIGURATION: $ConfName

  # Note that we're running the tests using the version of the code in the
  # builddir, not in the buildroot.

  # Run the upstream test suite, setting "WITHIN_PYTHON_RPM_BUILD" so that the
  # our non-standard decorators take effect on the relevant tests:
  #   @unittest._skipInRpmBuild(reason)
  #   @unittest._expectedFailureInRpmBuild
  # test_faulthandler.test_register_chain currently fails on ppc64le and
  #   aarch64, see upstream bug http://bugs.python.org/issue21131
  WITHIN_PYTHON_RPM_BUILD= \
  LD_LIBRARY_PATH=$ConfDir $ConfDir/python -m test.regrtest \
    -wW --slowest --findleaks \
    -x test_bdist_rpm \
    %ifarch %{mips64}
    -x test_ctypes \
    %endif

  echo FINISHED: CHECKING OF PYTHON FOR CONFIGURATION: $ConfName

}

%if %{with tests}

# Check each of the configurations:
%if %{with debug_build}
CheckPython debug
%endif # with debug_build
CheckPython optimized

%endif # with tests


%post -n platform-python
# Default with no /usr/bin/python symlink
alternatives --install %{_bindir}/unversioned-python \
                       python \
                       %{_libexecdir}/no-python \
                       404 \
             --slave   %{_mandir}/man1/python.1.gz \
                       unversioned-python-man \
                       %{_mandir}/man1/unversioned-python.1.gz

%postun -n platform-python
# Do this only during uninstall process (not during update)
if [ $1 -eq 0 ]; then
    alternatives --keep-foreign --remove python \
                          %{_libexecdir}/no-python

fi


%post -n python3-idle
alternatives --add-slave python3 %{_bindir}/python3.6 \
    %{_bindir}/idle3 \
    idle3 \
    %{_bindir}/idle3.6

%postun -n python3-idle
# Do this only during uninstall process (not during update)
if [ $1 -eq 0 ]; then
    alternatives --keep-foreign --remove-slave python3 %{_bindir}/python3.6 \
       idle3
fi


%files -n platform-python
%license LICENSE
%doc README.rst
%{_bindir}/pydoc*

%exclude %{_bindir}/python3
%exclude %{_bindir}/python%{pybasever}
%exclude %{_bindir}/python%{LDVERSION_optimized}
%{_libexecdir}/platform-python
%{_libexecdir}/platform-python%{pybasever}
%{_libexecdir}/platform-python%{LDVERSION_optimized}
%{_libexecdir}/no-python
%ghost %{_bindir}/unversioned-python
%ghost %{_mandir}/man1/python.1.gz

%exclude %{_bindir}/pyvenv
%{_bindir}/pyvenv-%{pybasever}

%{_mandir}/man1/python3.6.1*
%{_mandir}/man1/unversioned-python.1*

%files libs
%license LICENSE
%doc README.rst

%dir %{pylibdir}
%dir %{dynload_dir}

%{pylibdir}/lib2to3
%exclude %{pylibdir}/lib2to3/tests

%dir %{pylibdir}/unittest/
%dir %{pylibdir}/unittest/__pycache__/
%{pylibdir}/unittest/*.py
%{pylibdir}/unittest/__pycache__/*%{bytecode_suffixes}

%dir %{pylibdir}/asyncio/
%dir %{pylibdir}/asyncio/__pycache__/
%{pylibdir}/asyncio/*.py
%{pylibdir}/asyncio/__pycache__/*%{bytecode_suffixes}

%dir %{pylibdir}/venv/
%dir %{pylibdir}/venv/__pycache__/
%{pylibdir}/venv/*.py
%{pylibdir}/venv/__pycache__/*%{bytecode_suffixes}
%{pylibdir}/venv/scripts

%{pylibdir}/wsgiref
%{pylibdir}/xmlrpc

%dir %{pylibdir}/ensurepip/
%dir %{pylibdir}/ensurepip/__pycache__/
%{pylibdir}/ensurepip/*.py
%{pylibdir}/ensurepip/__pycache__/*%{bytecode_suffixes}
%if %{with rpmwheels}
%exclude %{pylibdir}/ensurepip/_bundled
%else
%dir %{pylibdir}/ensurepip/_bundled
%{pylibdir}/ensurepip/_bundled/*.whl
%endif

# The majority of the test module lives in the test subpackage
# However test.support is in libs - it contains stuff used when testing your code
# https://bugzilla.redhat.com/show_bug.cgi?id=1651215
%dir %{pylibdir}/test/
%dir %{pylibdir}/test/__pycache__/
%dir %{pylibdir}/test/support/
%dir %{pylibdir}/test/support/__pycache__/
%{pylibdir}/test/__init__.py
%{pylibdir}/test/__pycache__/__init__%{bytecode_suffixes}
%{pylibdir}/test/support/*.py
%{pylibdir}/test/support/__pycache__/*%{bytecode_suffixes}

%dir %{pylibdir}/concurrent/
%dir %{pylibdir}/concurrent/__pycache__/
%{pylibdir}/concurrent/*.py
%{pylibdir}/concurrent/__pycache__/*%{bytecode_suffixes}

%dir %{pylibdir}/concurrent/futures/
%dir %{pylibdir}/concurrent/futures/__pycache__/
%{pylibdir}/concurrent/futures/*.py
%{pylibdir}/concurrent/futures/__pycache__/*%{bytecode_suffixes}

%{pylibdir}/pydoc_data

%{dynload_dir}/_blake2.%{SOABI_optimized}.so
%{dynload_dir}/_sha3.%{SOABI_optimized}.so
%{dynload_dir}/_hmacopenssl.%{SOABI_optimized}.so

%{dynload_dir}/_asyncio.%{SOABI_optimized}.so
%{dynload_dir}/_bisect.%{SOABI_optimized}.so
%{dynload_dir}/_bz2.%{SOABI_optimized}.so
%{dynload_dir}/_codecs_cn.%{SOABI_optimized}.so
%{dynload_dir}/_codecs_hk.%{SOABI_optimized}.so
%{dynload_dir}/_codecs_iso2022.%{SOABI_optimized}.so
%{dynload_dir}/_codecs_jp.%{SOABI_optimized}.so
%{dynload_dir}/_codecs_kr.%{SOABI_optimized}.so
%{dynload_dir}/_codecs_tw.%{SOABI_optimized}.so
%{dynload_dir}/_crypt.%{SOABI_optimized}.so
%{dynload_dir}/_csv.%{SOABI_optimized}.so
%{dynload_dir}/_ctypes.%{SOABI_optimized}.so
%{dynload_dir}/_curses.%{SOABI_optimized}.so
%{dynload_dir}/_curses_panel.%{SOABI_optimized}.so
%{dynload_dir}/_dbm.%{SOABI_optimized}.so
%{dynload_dir}/_decimal.%{SOABI_optimized}.so
%{dynload_dir}/_elementtree.%{SOABI_optimized}.so
%if %{with gdbm}
%{dynload_dir}/_gdbm.%{SOABI_optimized}.so
%endif
%{dynload_dir}/_hashlib.%{SOABI_optimized}.so
%{dynload_dir}/_heapq.%{SOABI_optimized}.so
%{dynload_dir}/_json.%{SOABI_optimized}.so
%{dynload_dir}/_lsprof.%{SOABI_optimized}.so
%{dynload_dir}/_lzma.%{SOABI_optimized}.so
%{dynload_dir}/_multibytecodec.%{SOABI_optimized}.so
%{dynload_dir}/_multiprocessing.%{SOABI_optimized}.so
%{dynload_dir}/_opcode.%{SOABI_optimized}.so
%{dynload_dir}/_pickle.%{SOABI_optimized}.so
%{dynload_dir}/_posixsubprocess.%{SOABI_optimized}.so
%{dynload_dir}/_random.%{SOABI_optimized}.so
%{dynload_dir}/_socket.%{SOABI_optimized}.so
%{dynload_dir}/_sqlite3.%{SOABI_optimized}.so
%{dynload_dir}/_ssl.%{SOABI_optimized}.so
%{dynload_dir}/_struct.%{SOABI_optimized}.so
%{dynload_dir}/array.%{SOABI_optimized}.so
%{dynload_dir}/audioop.%{SOABI_optimized}.so
%{dynload_dir}/binascii.%{SOABI_optimized}.so
%{dynload_dir}/cmath.%{SOABI_optimized}.so
%{dynload_dir}/_datetime.%{SOABI_optimized}.so
%{dynload_dir}/fcntl.%{SOABI_optimized}.so
%{dynload_dir}/grp.%{SOABI_optimized}.so
%{dynload_dir}/math.%{SOABI_optimized}.so
%{dynload_dir}/mmap.%{SOABI_optimized}.so
%{dynload_dir}/nis.%{SOABI_optimized}.so
%{dynload_dir}/ossaudiodev.%{SOABI_optimized}.so
%{dynload_dir}/parser.%{SOABI_optimized}.so
%{dynload_dir}/pyexpat.%{SOABI_optimized}.so
%{dynload_dir}/readline.%{SOABI_optimized}.so
%{dynload_dir}/resource.%{SOABI_optimized}.so
%{dynload_dir}/select.%{SOABI_optimized}.so
%{dynload_dir}/spwd.%{SOABI_optimized}.so
%{dynload_dir}/syslog.%{SOABI_optimized}.so
%{dynload_dir}/termios.%{SOABI_optimized}.so
%{dynload_dir}/_testmultiphase.%{SOABI_optimized}.so
%{dynload_dir}/unicodedata.%{SOABI_optimized}.so
%{dynload_dir}/xxlimited.%{SOABI_optimized}.so
%{dynload_dir}/zlib.%{SOABI_optimized}.so

%dir %{pylibdir}/site-packages/
%dir %{pylibdir}/site-packages/__pycache__/
%{pylibdir}/site-packages/README.txt
%{pylibdir}/*.py
%dir %{pylibdir}/__pycache__/
%{pylibdir}/__pycache__/*%{bytecode_suffixes}

%dir %{pylibdir}/collections/
%dir %{pylibdir}/collections/__pycache__/
%{pylibdir}/collections/*.py
%{pylibdir}/collections/__pycache__/*%{bytecode_suffixes}

%dir %{pylibdir}/ctypes/
%dir %{pylibdir}/ctypes/__pycache__/
%{pylibdir}/ctypes/*.py
%{pylibdir}/ctypes/__pycache__/*%{bytecode_suffixes}
%{pylibdir}/ctypes/macholib

%{pylibdir}/curses

%dir %{pylibdir}/dbm/
%dir %{pylibdir}/dbm/__pycache__/
%{pylibdir}/dbm/*.py
%{pylibdir}/dbm/__pycache__/*%{bytecode_suffixes}

%dir %{pylibdir}/distutils/
%dir %{pylibdir}/distutils/__pycache__/
%{pylibdir}/distutils/*.py
%{pylibdir}/distutils/__pycache__/*%{bytecode_suffixes}
%{pylibdir}/distutils/README
%{pylibdir}/distutils/command
%exclude %{pylibdir}/distutils/command/wininst-*.exe

%dir %{pylibdir}/email/
%dir %{pylibdir}/email/__pycache__/
%{pylibdir}/email/*.py
%{pylibdir}/email/__pycache__/*%{bytecode_suffixes}
%{pylibdir}/email/mime
%doc %{pylibdir}/email/architecture.rst

%{pylibdir}/encodings

%{pylibdir}/html
%{pylibdir}/http

%dir %{pylibdir}/importlib/
%dir %{pylibdir}/importlib/__pycache__/
%{pylibdir}/importlib/*.py
%{pylibdir}/importlib/__pycache__/*%{bytecode_suffixes}

%dir %{pylibdir}/json/
%dir %{pylibdir}/json/__pycache__/
%{pylibdir}/json/*.py
%{pylibdir}/json/__pycache__/*%{bytecode_suffixes}

%{pylibdir}/logging
%{pylibdir}/multiprocessing

%dir %{pylibdir}/sqlite3/
%dir %{pylibdir}/sqlite3/__pycache__/
%{pylibdir}/sqlite3/*.py
%{pylibdir}/sqlite3/__pycache__/*%{bytecode_suffixes}

%exclude %{pylibdir}/turtle.py
%exclude %{pylibdir}/__pycache__/turtle*%{bytecode_suffixes}

%{pylibdir}/urllib
%{pylibdir}/xml

%if "%{_lib}" == "lib64"
%attr(0755,root,root) %dir %{_prefix}/lib/python%{pybasever}
%attr(0755,root,root) %dir %{_prefix}/lib/python%{pybasever}/site-packages
%attr(0755,root,root) %dir %{_prefix}/lib/python%{pybasever}/site-packages/__pycache__/
%endif

# "Makefile" and the config-32/64.h file are needed by
# distutils/sysconfig.py:_init_posix(), so we include them in the core
# package, along with their parent directories (bug 531901):
%dir %{pylibdir}/config-%{LDVERSION_optimized}-%{platform_triplet}/
%{pylibdir}/config-%{LDVERSION_optimized}-%{platform_triplet}/Makefile
%dir %{_includedir}/python%{LDVERSION_optimized}/
%{_includedir}/python%{LDVERSION_optimized}/%{_pyconfig_h}

%{_libdir}/%{py_INSTSONAME_optimized}
%{_libdir}/libpython3.so

%files devel


%files -n platform-python-devel
%{_bindir}/2to3
# TODO: Remove 2to3-3.7 once rebased to 3.7
%{_bindir}/2to3-%{pybasever}
%{pylibdir}/config-%{LDVERSION_optimized}-%{platform_triplet}/*
%exclude %{pylibdir}/config-%{LDVERSION_optimized}-%{platform_triplet}/Makefile
%exclude %{pylibdir}/distutils/command/wininst-*.exe
%{_includedir}/python%{LDVERSION_optimized}/*.h
%exclude %{_includedir}/python%{LDVERSION_optimized}/%{_pyconfig_h}
%doc Misc/README.valgrind Misc/valgrind-python.supp Misc/gdbinit

%exclude %{_bindir}/python3-config
%exclude %{_bindir}/python%{pybasever}-config
%exclude %{_bindir}/python%{LDVERSION_optimized}-config
%exclude %{_bindir}/python%{LDVERSION_optimized}-*-config
%{_libexecdir}/platform-python-config
%{_libexecdir}/platform-python%{pybasever}-config
%{_libexecdir}/platform-python%{LDVERSION_optimized}-config
%{_libexecdir}/platform-python%{LDVERSION_optimized}-*-config

%{_bindir}/pathfix.py
%{_libdir}/libpython%{LDVERSION_optimized}.so
%{_libdir}/pkgconfig/python-%{LDVERSION_optimized}.pc
%{_libdir}/pkgconfig/python-%{pybasever}.pc
%{_libdir}/pkgconfig/python3.pc

%files idle
%{_bindir}/idle%{pybasever}
%{pylibdir}/idlelib
%{_metainfodir}/idle3.appdata.xml
%{_datadir}/applications/idle3.desktop
%{_datadir}/icons/hicolor/*/apps/idle3.*
%ghost %{_bindir}/idle3

%files tkinter
%{pylibdir}/tkinter
%exclude %{pylibdir}/tkinter/test
%{dynload_dir}/_tkinter.%{SOABI_optimized}.so
%{pylibdir}/turtle.py
%{pylibdir}/__pycache__/turtle*%{bytecode_suffixes}
%dir %{pylibdir}/turtledemo
%{pylibdir}/turtledemo/*.py
%{pylibdir}/turtledemo/*.cfg
%dir %{pylibdir}/turtledemo/__pycache__/
%{pylibdir}/turtledemo/__pycache__/*%{bytecode_suffixes}

%files test
%{pylibdir}/ctypes/test
%{pylibdir}/distutils/tests
%{pylibdir}/sqlite3/test
%{pylibdir}/test
%{dynload_dir}/_ctypes_test.%{SOABI_optimized}.so
%{dynload_dir}/_testbuffer.%{SOABI_optimized}.so
%{dynload_dir}/_testcapi.%{SOABI_optimized}.so
%{dynload_dir}/_testimportmultiple.%{SOABI_optimized}.so
%{pylibdir}/lib2to3/tests
%{pylibdir}/tkinter/test
%{pylibdir}/unittest/test

# stuff already owned by the libs subpackage
# test requires libs, so we are safe not owning those dirs
%exclude %dir %{pylibdir}/test/
%exclude %dir %{pylibdir}/test/__pycache__/
%exclude %{pylibdir}/test/__init__.py
%exclude %{pylibdir}/test/__pycache__/__init__%{bytecode_suffixes}
%exclude %{pylibdir}/test/support/

# We don't bother splitting the debug build out into further subpackages:
# if you need it, you're probably a developer.

# Hence the manifest is the combination of analogous files in the manifests of
# all of the other subpackages

%if %{with debug_build}
%files -n platform-python-debug
# Analog of the core subpackage's files:
%exclude %{_bindir}/python%{LDVERSION_debug}
%{_libexecdir}/platform-python%{LDVERSION_debug}
%exclude %{_bindir}/python3-debug
%{_libexecdir}/platform-python-debug

# Analog of the -libs subpackage's files:
# ...with debug builds of the built-in "extension" modules:

%{dynload_dir}/_blake2.%{SOABI_debug}.so
%{dynload_dir}/_sha3.%{SOABI_debug}.so
%{dynload_dir}/_hmacopenssl.%{SOABI_debug}.so

%{dynload_dir}/_asyncio.%{SOABI_debug}.so
%{dynload_dir}/_bisect.%{SOABI_debug}.so
%{dynload_dir}/_bz2.%{SOABI_debug}.so
%{dynload_dir}/_codecs_cn.%{SOABI_debug}.so
%{dynload_dir}/_codecs_hk.%{SOABI_debug}.so
%{dynload_dir}/_codecs_iso2022.%{SOABI_debug}.so
%{dynload_dir}/_codecs_jp.%{SOABI_debug}.so
%{dynload_dir}/_codecs_kr.%{SOABI_debug}.so
%{dynload_dir}/_codecs_tw.%{SOABI_debug}.so
%{dynload_dir}/_crypt.%{SOABI_debug}.so
%{dynload_dir}/_csv.%{SOABI_debug}.so
%{dynload_dir}/_ctypes.%{SOABI_debug}.so
%{dynload_dir}/_curses.%{SOABI_debug}.so
%{dynload_dir}/_curses_panel.%{SOABI_debug}.so
%{dynload_dir}/_dbm.%{SOABI_debug}.so
%{dynload_dir}/_decimal.%{SOABI_debug}.so
%{dynload_dir}/_elementtree.%{SOABI_debug}.so
%if %{with gdbm}
%{dynload_dir}/_gdbm.%{SOABI_debug}.so
%endif
%{dynload_dir}/_hashlib.%{SOABI_debug}.so
%{dynload_dir}/_heapq.%{SOABI_debug}.so
%{dynload_dir}/_json.%{SOABI_debug}.so
%{dynload_dir}/_lsprof.%{SOABI_debug}.so
%{dynload_dir}/_lzma.%{SOABI_debug}.so
%{dynload_dir}/_multibytecodec.%{SOABI_debug}.so
%{dynload_dir}/_multiprocessing.%{SOABI_debug}.so
%{dynload_dir}/_opcode.%{SOABI_debug}.so
%{dynload_dir}/_pickle.%{SOABI_debug}.so
%{dynload_dir}/_posixsubprocess.%{SOABI_debug}.so
%{dynload_dir}/_random.%{SOABI_debug}.so
%{dynload_dir}/_socket.%{SOABI_debug}.so
%{dynload_dir}/_sqlite3.%{SOABI_debug}.so
%{dynload_dir}/_ssl.%{SOABI_debug}.so
%{dynload_dir}/_struct.%{SOABI_debug}.so
%{dynload_dir}/array.%{SOABI_debug}.so
%{dynload_dir}/audioop.%{SOABI_debug}.so
%{dynload_dir}/binascii.%{SOABI_debug}.so
%{dynload_dir}/cmath.%{SOABI_debug}.so
%{dynload_dir}/_datetime.%{SOABI_debug}.so
%{dynload_dir}/fcntl.%{SOABI_debug}.so
%{dynload_dir}/grp.%{SOABI_debug}.so
%{dynload_dir}/math.%{SOABI_debug}.so
%{dynload_dir}/mmap.%{SOABI_debug}.so
%{dynload_dir}/nis.%{SOABI_debug}.so
%{dynload_dir}/ossaudiodev.%{SOABI_debug}.so
%{dynload_dir}/parser.%{SOABI_debug}.so
%{dynload_dir}/pyexpat.%{SOABI_debug}.so
%{dynload_dir}/readline.%{SOABI_debug}.so
%{dynload_dir}/resource.%{SOABI_debug}.so
%{dynload_dir}/select.%{SOABI_debug}.so
%{dynload_dir}/spwd.%{SOABI_debug}.so
%{dynload_dir}/syslog.%{SOABI_debug}.so
%{dynload_dir}/termios.%{SOABI_debug}.so
%{dynload_dir}/_testmultiphase.%{SOABI_debug}.so
%{dynload_dir}/unicodedata.%{SOABI_debug}.so
%{dynload_dir}/zlib.%{SOABI_debug}.so

# No need to split things out the "Makefile" and the config-32/64.h file as we
# do for the regular build above (bug 531901), since they're all in one package
# now; they're listed below, under "-devel":

%{_libdir}/%{py_INSTSONAME_debug}

# Analog of the -devel subpackage's files:
%{pylibdir}/config-%{LDVERSION_debug}-%{platform_triplet}
%{_includedir}/python%{LDVERSION_debug}

%exclude %{_bindir}/python%{LDVERSION_debug}-config
%exclude %{_bindir}/python%{LDVERSION_debug}-*-config
%{_libexecdir}/platform-python%{LDVERSION_debug}-config
%{_libexecdir}/platform-python%{LDVERSION_debug}-*-config

%{_libdir}/libpython%{LDVERSION_debug}.so
%{_libdir}/libpython%{LDVERSION_debug}.so.1.0
%{_libdir}/pkgconfig/python-%{LDVERSION_debug}.pc

# Analog of the -tools subpackage's files:
#  None for now; we could build precanned versions that have the appropriate
# shebang if needed

# Analog  of the tkinter subpackage's files:
%{dynload_dir}/_tkinter.%{SOABI_debug}.so

# Analog  of the -test subpackage's files:
%{dynload_dir}/_ctypes_test.%{SOABI_debug}.so
%{dynload_dir}/_testbuffer.%{SOABI_debug}.so
%{dynload_dir}/_testcapi.%{SOABI_debug}.so
%{dynload_dir}/_testimportmultiple.%{SOABI_debug}.so

%endif # with debug_build

# We put the debug-gdb.py file inside /usr/lib/debug to avoid noise from ldconfig
# See https://bugzilla.redhat.com/show_bug.cgi?id=562980
#
# The /usr/lib/rpm/redhat/macros defines %%__debug_package to use
# debugfiles.list, and it appears that everything below /usr/lib/debug and
# (/usr/src/debug) gets added to this file (via LISTFILES) in
# /usr/lib/rpm/find-debuginfo.sh
#
# Hence by installing it below /usr/lib/debug we ensure it is added to the
# -debuginfo subpackage
# (if it doesn't, then the rpmbuild ought to fail since the debug-gdb.py
# payload file would be unpackaged)

# Workaround for https://bugzilla.redhat.com/show_bug.cgi?id=1476593
%undefine _debuginfo_subpackages

# ======================================================
# Finally, the changelog:
# ======================================================

%changelog
* Wed Nov 15 2023 Release Engineering <releng@openela.org> - %{pybasever}.8.openela.0
- Add openela to supported dists

* Thu Sep 07 2023 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-56
- Security fix for CVE-2023-40217
Resolves: RHEL-3041

* Wed Aug 09 2023 Petr Viktorin <pviktori@redhat.com> - 3.6.8-55
- Fix symlink handling in the fix for CVE-2007-4559
Resolves: rhbz#263261

* Fri Jul 07 2023 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-54
- Bump release for rebuild
Resolves: rhbz#2173917

* Fri Jun 30 2023 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-53
- Security fix for CVE-2023-24329
Resolves: rhbz#2173917

* Tue Jun 06 2023 Petr Viktorin <pviktori@redhat.com> - 3.6.8-52
- Add filters for tarfile extraction (CVE-2007-4559, PEP-706)
Resolves: rhbz#263261

* Tue Jan 24 2023 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-51
- Properly strip the LTO bytecode from python.o
Resolves: rhbz#2137707

* Wed Dec 21 2022 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-50
- Security fix for CVE-2022-45061
- Strip the LTO bytecode from python.o
Resolves: rhbz#2144072, rhbz#2137707

* Tue Oct 25 2022 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-49
- Security fixes for CVE-2020-10735 and CVE-2021-28861
Resolves: rhbz#1834423, rhbz#2120642

* Thu Oct 20 2022 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-48
- Release bump
Resolves: rhbz#2136435

* Tue Jun 14 2022 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-47
- Security fix for CVE-2015-20107
Resolves: rhbz#2075390

* Wed Mar 09 2022 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-46
- Security fix for CVE-2022-0391: urlparse does not sanitize URLs containing ASCII newline and tabs
- Fix the test suite support for Expat >= 2.4.5
Resolves: rhbz#2047376, rhbz#2060435

* Fri Jan 07 2022 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-45
- Security fix for CVE-2021-4189: ftplib should not use the host from the PASV response
Resolves: rhbz#2036020

* Tue Oct 12 2021 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-44
- Use the monotonic clock for theading.Condition
- Use the monotonic clock for the global interpreter lock
Resolves: rhbz#2003758

* Mon Oct 11 2021 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-43
- Change shouldRollover() methods of logging.handlers to only rollover regular files
Resolves: rhbz#2009200

* Fri Sep 17 2021 Lumír Balhar <lbalhar@redhat.com> - 3.6.8-42
- Security fix for CVE-2021-3737
Resolves: rhbz#1995162

* Thu Sep 09 2021 Lumír Balhar <lbalhar@redhat.com> - 3.6.8-41
- Security fix for CVE-2021-3733: Denial of service when identifying crafted invalid RFCs
Resolves: rhbz#1995234

* Thu Jul 29 2021 Tomas Orsava <torsava@redhat.com> - 3.6.8-40
- Adjusted the postun scriptlets to enable upgrading to RHEL 9
- Resolves: rhbz#1933055

* Fri Jul 09 2021 Victor Stinner <vstinner@redhat.com> - 3.6.8-39
- Fix reentrant call to threading.enumerate() (rhbz#1959459)
- Don't exit Python with abort() when a thread exit and there is no available
  file descriptor to load dynamically the libgcc_s.so.1 library (rhbz#1972293)

* Fri Apr 30 2021 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-38
- Security fix for CVE-2021-3426: information disclosure via pydoc
Resolves: rhbz#1935913

* Thu Mar 04 2021 Petr Viktorin <pviktori@redhat.com> - 3.6.8-37
- Fix for CVE-2021-23336
Resolves: rhbz#1928904

* Fri Jan 22 2021 Lumír Balhar <lbalhar@redhat.com> - 3.6.8-36
- Fix for CVE-2021-3177
Resolves: rhbz#1918168

* Mon Jan 18 2021 Lumír Balhar <lbalhar@redhat.com> - 3.6.8-35
- New options -a and -k for pathfix.py script backported from upstream
Resolves: rhbz#1917691

* Fri Dec 04 2020 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-34
- Security fix for CVE-2020-27619: eval() call on content received via HTTP in the CJK codec tests
Resolves: rhbz#1890237

* Tue Nov 24 2020 Lumír Balhar <lbalhar@redhat.com> - 3.6.8-33
- Add support for upstream architecture names
https: //fedoraproject.org/wiki/Changes/Python_Upstream_Architecture_Names
Resolves: rhbz#1868003

* Mon Nov 09 2020 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-32
- Security fix for CVE-2020-26116: Reject control chars in HTTP method in http.client
Resolves: rhbz#1883257

* Mon Aug 17 2020 Tomas Orsava <torsava@redhat.com> - 3.6.8-31
- Avoid infinite loop when reading specially crafted TAR files (CVE-2019-20907)
Resolves: rhbz#1856481
- Resolve hash collisions for Pv4Interface and IPv6Interface (CVE-2020-14422)
Resolves: rhbz#1854926

* Thu Jun 25 2020 Victor Stinner <vstinner@python.org> - 3.6.8-30
- Remove downstream 00178-dont-duplicate-flags-in-sysconfig.patch which
  introduced a bug on distutils.sysconfig.get_config_var('LIBPL')
  (rhbz#1851090).

* Thu Jun 18 2020 Victor Stinner <vstinner@python.org> - 3.6.8-29
- Fix python3-config --configdir (rhbz#1772992).

* Fri Apr 03 2020 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-28
- Security fix for CVE-2020-8492
Resolves: rhbz#1810618

* Tue Mar 31 2020 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-27
- Add a sentinel value on the Hmac_members table of the fips compliant hmac module
Resolves: rhbz#1800512

* Mon Mar 23 2020 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-26
- Skip test_startup_imports from test_site if we have a .pth file in sys.path
Resolves: rhbz#1814392

* Fri Mar 20 2020 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-25
- Security fix for CVE-2019-16935
Resolves: rhbz#1798001

* Mon Mar 16 2020 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-24
- Build Python with -fno-semantic-interposition for better performance
- https://fedoraproject.org/wiki/Changes/PythonNoSemanticInterpositionSpeedup
- Also fix test_gdb failures with Link Time Optimizations
Resolves: rhbz#1724996

* Wed Nov 27 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-23
- Modify the test suite to better handle disabled SSL/TLS versions and FIPS mode
- Use OpenSSL's DRBG and disable os.getrandom() function in FIPS mode
Resolves: rhbz#1754028, rhbz#1754027, rhbz#1754026, rhbz#1774471

* Thu Oct 24 2019 Tomas Orsava <torsava@redhat.com> - 3.6.8-22
- Changed Requires into Recommends for python3-pip to allow a lower RHEL8
  footprint for containers and other minimal environments
Resolves: rhbz#1756217

* Wed Oct 16 2019 Tomas Orsava <torsava@redhat.com> - 3.6.8-21
- Patch 329 (FIPS) modified: Added workaround for mod_ssl:
  Skip error checking in _Py_hashlib_fips_error
Resolves: rhbz#1760106

* Mon Oct 14 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-20
- Security fix for CVE-2019-16056
Resolves: rhbz#1750776

* Wed Oct 09 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-19
- Skip windows specific test_get_exe_bytes test case and enable test_distutils
Resolves: rhbz#1754040

* Mon Oct 07 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-18
- Reduce the number of tests running during the profile guided optimizations build
- Enable profile guided optimizations for all the supported architectures
Resolves: rhbz#1749576

* Mon Oct 07 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-17
- Security fix for CVE-2018-20852
Resolves: rhbz#1741553

* Fri Oct 04 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-16
- Properly pass the -Og optimization flag to the debug build
Resolves: rhbz#1712977 and rhbz#1714733

* Thu Aug 29 2019 Tomas Orsava <torsava@redhat.com> - 3.6.8-15
- Patch 329 that adds support for OpenSSL FIPS mode has been improved and
  bugfixed
Resolves: rhbz#1744670 rhbz#1745499 rhbz#1745685

* Tue Aug 06 2019 Tomas Orsava <torsava@redhat.com> - 3.6.8-14
- Adding a new patch 329 that adds support for OpenSSL FIPS mode
- Explicitly listing man pages in files section to fix an RPM warning
Resolves: rhbz#1731424

* Tue Jul 02 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-13
- Do not set PHA verify flag on client side (rhbz#1725721)
- Enable TLS 1.3 post-handshake authentication in http.client (rhbz#1671353)

* Fri Jun 21 2019 Miro Hrončok <mhroncok@redhat.com> - 3.6.8-12
- Use RPM built wheels of pip and setuptools in ensurepip instead of our rewheel patch
- Require platform-python-setuptools from platform-python-devel to prevent packaging errors
Resolves: rhbz#1701286

* Fri Jun 07 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-11
- Fix for CVE-2019-10160
Resolves: rhbz#1689318

* Wed May 29 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-10
- Security fix for CVE-2019-9948
Resolves: rhbz#1714643

* Tue May 21 2019 Miro Hrončok <mhroncok@redhat.com> - 3.6.8-9
- Reduced default build flags used to build extension modules
  https://fedoraproject.org/wiki/Changes/Python_Extension_Flags
Resolves: rhbz#1634784

* Mon May 13 2019 Tomas Orsava <torsava@redhat.com> - 3.6.8-8
- gzip the unversioned-python man page
Resolves: rhbz#1665514

* Wed May 08 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-7
- Disallow control chars in http URLs
- Fixes CVE-2019-9740 and CVE-2019-9947
Resolves: rhbz#1704365 and rhbz#1703531

* Fri May 03 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-6
- Updated fix for CVE-2019-9636 (rhbz#1689318)

* Wed Apr 3 2019 Miro Hrončok <mhroncok@redhat.com> - 3.6.8-5
- Security fix for CVE-2019-9636 (rhbz#1689318)

* Wed Mar 20 2019 Victor Stinner <vstinner@redhat.com> - 3.6.8-4
- Security fix for CVE-2019-5010 (rhbz#1666789)

* Wed Mar 13 2019 Victor Stinner <vstinner@redhat.com> - 3.6.8-3
- Fix test_tarfile on ppc64 (rhbz#1639490)

* Fri Jan 18 2019 Victor Stinner <vstinner@redhat.com> - 3.6.8-2
- test_ssl fixes for TLS 1.3 and OpenSSL 1.1.1 (rhbz#1639531)

* Wed Jan 09 2019 Charalampos Stratakis <cstratak@redhat.com> - 3.6.8-1
- Update to 3.6.8
Resolves: rhbz#1658271

* Wed Nov 21 2018 Miro Hrončok <mhroncok@redhat.com> - 3.6.7-4
- Make sure the entire test.support module is in python3-libs
Resolves: rhbz#1651215

* Tue Nov 13 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.7-3
- Add choices for sort option of cProfile for better output
Resolves: rhbz#1640151

* Mon Nov 05 2018 Tomas Orsava <torsava@redhat.com> - 3.6.7-2
- Switch to requiring platform-python-pip/setuptools instead of the python3-
  versions
- Resolves: rhbz#1638836

* Thu Oct 25 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.7-1
- Update to 3.6.7 (rhbz#1627739)
- Re-enable test_gdb (rhbz#1639536)
- Re-enable test_faulthandler (rhbz#1640147)

* Tue Oct 16 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.6-19
- Add compatibility fixes for openssl 1.1.1 and tls 1.3
Resolves: rhbz#1610023

* Tue Oct 16 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.6-18
- Fix test_dbm_gnu for gdbm 1.15 which fails on ppc64le
Resolves: rhbz#1638710

* Sun Oct 14 2018 Tomas Orsava <torsava@redhat.com> - 3.6.6-17
- Add Requires (/post/postun) on /usr/sbin/alternatives
- Resolves: rhbz#1632625

* Fri Oct 12 2018 Petr Viktorin <pviktori@redhat.com> - 3.6.6-16
- Remove Windows binaries from the source archive
- Resolves: rhbz#1633219

* Wed Oct 10 2018 Petr Viktorin <pviktori@redhat.com> - 3.6.6-15
- Compile the debug build with -Og rather than -O0
- Resolves: rhbz#1624162

* Wed Oct 10 2018 Miro Hrončok <mhroncok@redhat.com> - 3.6.6-14
- Security fix for CVE-2018-14647
- Resolves: rhbz#1632096

* Sun Oct 07 2018 Tomas Orsava <torsava@redhat.com> - 3.6.6-13
- Stop providing the `python3` and `python3-debug` names from the
  platform-python/-debug subpackages
- The `python3` and `python3-debug` names are now provided from the python36
  component
- Conflict with older versions of `python3` and `python3-debug`
- Related: rhbz#1619153

* Tue Oct 02 2018 Tomas Orsava <torsava@redhat.com> - 3.6.6-12.2
- Fix update of idle3's alternative symlink
- Resolves: rhbz#1632625

* Mon Oct 01 2018 Tomas Orsava <torsava@redhat.com> - 3.6.6-12.1
- Add idle3 to the alternatives system
- Resolves: rhbz#1632625

* Fri Sep 28 2018 Tomas Orsava <torsava@redhat.com> - 3.6.6-12
- Rename the python3-debug subpackage to platform-python-debug
- Provide the `python3-debug` name for backwards compatibility until it's taken
  over by the python36 component
- Rename the python3-libs-devel subpackage to platform-python-devel for
  symmetry with the `platform-python` and `platform-python-debug` package
- Add symlink /usr/libexec/platform-python-debug that was mistakenly omitted
- Related: rhbz#1619153

* Fri Sep 28 2018 Tomas Orsava <torsava@redhat.com> - 3.6.6-11
- Implement `alternatives` for chosing /usr/bin/python
- Provide the default `no-python` alternative
- Resolves: rhbz#1632625

* Wed Sep 19 2018 Tomas Orsava <torsava@redhat.com> - 3.6.6-10
- Provide the `python3` name with _isa until some packages can be rebuilt
- Resolves: rhbz#1619153

* Tue Sep 11 2018 Tomas Orsava <torsava@redhat.com> - 3.6.6-9
- Rename the python3 subpackage to platform-python
- Provide the `python3` name for backwards compatibility until it's taken over
  by the python36 component
- The python36 component that contains /usr/bin/python3 will Provide the
  name `python3` in its upcoming update
- Resolves: rhbz#1619153

* Tue Sep 04 2018 Lumír Balhar <lbalhar@redhat.com> - 3.6.6-8
- Remove /usr/bin/idle3 symlink
- Resolves: rhbz#1623811

* Wed Aug 15 2018 Lumír Balhar <lbalhar@redhat.com> - 3.6.6-7
- Remove 3 > 3.6 symlinks for pydoc and python manpage
- Resolves: rhbz#1615727

* Sun Aug 12 2018 Troy Dawson <tdawson@redhat.com>
- Disable %check so package will build for Mass Rebuild
- Related: bug#1614611

* Mon Aug 06 2018 Petr Viktorin <pviktori@redhat.com> - 3.6.6-6
- Make `devel` subpackage require python36-devel again
  (and get /usr/bin/python3 and /usr/bin/python3-config from that).
- Remove /usr/bin/python3* executables
- Use pip36 instead of `pip3`

* Fri Aug 03 2018 Petr Viktorin <pviktori@redhat.com> - 3.6.6-5
- Fix the `devel` subpackage to require python3, rather than python36-devel,
  and provide /usr/bin/python3-config itself.

* Wed Aug 01 2018 Tomas Orsava <torsava@redhat.com> - 3.6.6-4
- Create the `libs-devel` subpackage and move `devel` contents there
- `devel` subpackage is only for the buildroot and requires `python36-devel`
  to get /usr/bin/python3{,-config} symlinks there
- `devel` subpackage will not be shipped into RHEL8, only `libs-devel` will
- `debug` subpackage now runtime requires `libs-devel` instead of `devel`

* Wed Aug 01 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.6-3
- Disable ssl related tests for now

* Wed Jul 25 2018 Petr Kubat <pkubat@redhat.com> - 3.6.6-2
- Rebuilt for gdbm

* Thu Jul 19 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.6-1
- Update to Python 3.6.6

* Thu Jul 19 2018 Tomas Orsava <torsava@redhat.com> - 3.6.5-7
- Fix %%py_byte_compile macro: when invoked with a Python 2 binary it also
  mistakenly ran py3_byte_compile

* Thu Jul 19 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.5-6
- Do not include the unversioned pyvenv binary in the rpm

* Tue Jul 03 2018 Tomas Orsava <torsava@redhat.com> - 3.6.5-5
- Remove old system-python Provides/Obsoletes/symlinks/patches from Fedora

* Wed May 09 2018 Tomas Orsava <torsava@redhat.com> - 3.6.5-4
- Switch all shebangs to point to the Platform-Python executables

* Wed May 09 2018 Tomas Orsava <torsava@redhat.com> - 3.6.5-3
- Platform-Python: Rebase implementation from RHEL8 Alpha:
- Move the main executable to /usr/libexec/platform-python
- Move /usr/bin/python*-config and /usr/bin/pythonX.Ym scripts to /usr/libexec/
- Provide symlink to the main executable and other scripts from /usr/bin/,
  these will be later shipped only in the python36 module

* Wed May 09 2018 Tomas Orsava <torsava@redhat.com> - 3.6.5-2
- Remove Obsoletes and Provides that are not relevant for RHEL

* Thu Mar 29 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.5-1
- Update to 3.6.5

* Sat Mar 24 2018 Miro Hrončok <mhroncok@redhat.com> - 3.6.4-20
- Fix broken macro invocation and broken building of C Python extensions
Resolves: rhbz#1560103

* Fri Mar 16 2018 Miro Hrončok <mhroncok@redhat.com> - 3.6.4-19
- Add -n option for pathfix.py
Resolves: rhbz#1546990

* Thu Mar 15 2018 Miro Hrončok <mhroncok@redhat.com> - 3.6.4-18
- Fix the py_byte_compile macro to work on Python 2
- Remove the pybytecompile macro file from the flat package
Resolves: rhbz#1484993

* Tue Mar 13 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.4-17
- Do not send IP addresses in SNI TLS extension

* Sat Feb 24 2018 Florian Weimer <fweimer@redhat.com> - 3.6.4-16
- Rebuild with new LDFLAGS from redhat-rpm-config

* Wed Feb 21 2018 Miro Hrončok <mhroncok@redhat.com> - 3.6.4-15
- Filter out automatic /usr/bin/python3.X requirement,
  recommend the main package from libs instead
Resolves: rhbz#1547131

* Thu Feb 15 2018 Iryna Shcherbina <ishcherb@redhat.com> - 3.6.4-14
- Remove the python3-tools package (#rhbz 1312030)
- Move /usr/bin/2to3 to python3-devel
- Move /usr/bin/idle and idlelib to python3-idle
- Provide python3-tools from python3-idle

* Fri Feb 09 2018 Igor Gnatenko <ignatenkobrain@fedoraproject.org> - 3.6.4-13
- Escape macros in %%changelog

* Fri Feb 02 2018 Michal Cyprian <mcyprian@redhat.com> - 3.6.4-12
- Remove sys.executable check from change-user-install-location patch
Resolves: rhbz#1532287

* Thu Feb 01 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.4-11
- Define TLS cipher suite on build time.

* Wed Jan 31 2018 Tomas Orsava <torsava@redhat.com> - 3.6.4-10
- Disable test_gdb for all arches and test_buffer for ppc64le in anticipation
  of the F28 mass rebuild
- Re-enable these tests after the mass rebuild when they can be properly
  addressed

* Tue Jan 23 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.4-9
- Restore the PyExc_RecursionErrorInst public symbol

* Tue Jan 23 2018 Björn Esser <besser82@fedoraproject.org> - 3.6.4-8
- Add patch to explicitly link _ctypes module with -ldl (#1537489)
- Refactored patch for libxcrypt
- Re-enable strict symbol checks in the link editor

* Mon Jan 22 2018 Björn Esser <besser82@fedoraproject.org> - 3.6.4-7
- Add patch for libxcrypt
- Disable strict symbol checks in the link editor

* Sat Jan 20 2018 Björn Esser <besser82@fedoraproject.org> - 3.6.4-6
- Rebuilt for switch to libxcrypt

* Fri Jan 19 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.4-5
- Fix localeconv() encoding for LC_NUMERIC

* Thu Jan 18 2018 Igor Gnatenko <ignatenkobrain@fedoraproject.org> - 3.6.4-4
- R: gdbm-devel → R: gdbm for python3-libs

* Wed Jan 17 2018 Miro Hrončok <mhroncok@redhat.com> - 3.6.4-3
- Require large enough gdbm (fixup for previous bump)

* Tue Jan 16 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.4-2
- Rebuild for reverted gdbm 1.13 on Fedora 27

* Mon Jan 15 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.4-1
- Update to version 3.6.4

* Fri Jan 12 2018 Charalampos Stratakis <cstratak@redhat.com> - 3.6.3-5
- Fix the compilation of the nis module.

* Tue Nov 21 2017 Miro Hrončok <mhroncok@redhat.com> - 3.6.3-4
- Raise the release of platform-python obsoletes for better maintainability

* Wed Nov 15 2017 Miro Hrončok <mhroncok@redhat.com> - 3.6.3-3
- Obsolete platform-python and it's subpackages

* Mon Oct 09 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.3-2
- Fix memory corruption due to allocator mix
Resolves: rhbz#1498207

* Fri Oct 06 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.3-1
- Update to Python 3.6.3

* Fri Sep 29 2017 Miro Hrončok <mhroncok@redhat.com> - 3.6.2-19
- Move pathfix.py to bindir, https://github.com/fedora-python/python-rpm-porting/issues/24
- Make the -devel package require redhat-rpm-config
Resolves: rhbz#1496757

* Wed Sep 13 2017 Iryna Shcherbina <ishcherb@redhat.com> - 3.6.2-18
- Fix /usr/bin/env dependency from python3-tools
Resolves: rhbz#1482118

* Wed Sep 06 2017 Iryna Shcherbina <ishcherb@redhat.com> - 3.6.2-17
- Include `-g` in the flags sent to the linker (LDFLAGS)
Resolves: rhbz#1483222

* Tue Sep 05 2017 Petr Viktorin <pviktori@redhat.com> - 3.6.2-16
- Specfile cleanup
- Make the main description also applicable to the SRPM
- Add audiotest.au to the test package

* Fri Sep 01 2017 Miro Hrončok <mhroncok@redhat.com> - 3.6.2-15
- Remove %%{pylibdir}/Tools/scripts/2to3

* Fri Sep 01 2017 Miro Hrončok <mhroncok@redhat.com> - 3.6.2-14
- Expat >= 2.1.0 is everywhere, remove explicit requires
- Conditionalize systemtap-devel BuildRequires
- For consistency, require /usr/sbin/ifconfig instead of net-tools

* Mon Aug 28 2017 Petr Viktorin <pviktori@redhat.com> - 3.6.2-13
- Rename patch files to be consistent
- Run autotools to generate the configure script before building
- Merge lib64 patches (104 into 102)
- Skip test_bdist_rpm using test config rather than a patch (removes patch 137)
- Remove patches 157 and 186, which had test changes left over after upstreaming
- Remove patch 188, a temporary workaround for hashlib tests
- Merge patches 180, 206, 243, 5001 (architecture naming) into new patch 274
- Move python2-tools conflicts to tools subpackage (it was wrongly in tkinter)

* Mon Aug 28 2017 Michal Cyprian <mcyprian@redhat.com> - 3.6.2-12
- Use python3 style of calling super() without arguments in rpath
  patch to prevent recursion in UnixCCompiler subclasses
Resolves: rhbz#1458122

* Mon Aug 21 2017 Petr Viktorin <pviktori@redhat.com> - 3.6.2-11
- Add bcond for --without optimizations
- Reword package descriptions
- Remove Group declarations
- Skip failing test_float_with_comma

* Mon Aug 21 2017 Miro Hrončok <mhroncok@redhat.com> - 3.6.2-10
- Remove system-python, see https://fedoraproject.org/wiki/Changes/Platform_Python_Stack

* Wed Aug 16 2017 Petr Viktorin <pviktori@redhat.com> - 3.6.2-9
- Use bconds for configuring the build
- Reorganize the initial sections

* Wed Aug 16 2017 Miro Hrončok <mhroncok@redhat.com> - 3.6.2-8
- Have /usr/bin/2to3 (rhbz#1111275)
- Provide 2to3 and idle3, list them in summary and description (rhbz#1076401)

* Fri Aug 11 2017 Michal Cyprian <mcyprian@redhat.com> - 3.6.2-7
- Revert "Add --executable option to install.py command"
  This enhancement is currently not needed and it can possibly
  collide with `pip --editable`option

* Mon Aug 07 2017 Iryna Shcherbina <ishcherb@redhat.com> - 3.6.2-6
- Fix the "urllib FTP protocol stream injection" vulnerability
Resolves: rhbz#1478916

* Tue Aug 01 2017 Tomas Orsava <torsava@redhat.com> - 3.6.2-5
- Dropped BuildRequires on db4-devel which was useful for Python 2 (module
  bsddb), however, no longer needod for Python 3
- Tested building Python 3 with and without the dependency, all tests pass and
  filelists of resulting RPMs are identical

* Sun Jul 30 2017 Florian Weimer <fweimer@redhat.com> - 3.6.2-4
- Do not generate debuginfo subpackages (#1476593)
- Rebuild with binutils fix for ppc64le (#1475636)

* Thu Jul 27 2017 Fedora Release Engineering <releng@fedoraproject.org> - 3.6.2-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Mass_Rebuild

* Tue Jul 25 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.2-2
- Make test_asyncio to not depend on the current SIGHUP signal handler.

* Tue Jul 18 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.2-1
- Update to Python 3.6.2

* Tue Jun 27 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.1-10
- Update to the latest upstream implementation of PEP 538

* Mon Jun 26 2017 Michal Cyprian <mcyprian@redhat.com> - 3.6.1-9
- Make pip and distutils in user environment install into separate location

* Fri Jun 23 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.1-8
- Fix test_alpn_protocols from test_ssl
- Do not require rebundled setuptools dependencies

* Tue May 16 2017 Tomas Orsava <torsava@redhat.com> - 3.6.1-7
- Added a dependency to the devel subpackage on python3-rpm-generators which
  have been excised out of rpm-build
- Updated notes on bootstrapping Python on top of this specfile accordingly
- Involves: rhbz#1410631, rhbz#1444925

* Tue May 09 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.1-6
- Enable profile guided optimizations for x86_64 and i686 architectures
- Update to a newer implementation of PEP 538
- Update description to reflect that Python 3 is now the default Python

* Fri May 05 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.1-5
- Update PEP 538 to the latest upstream implementation

* Tue Apr 18 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.1-4
- Enable link time optimizations
- Move windows executables to the devel subpackage (rhbz#1426257)

* Thu Apr 13 2017 Tomas Orsava <torsava@redhat.com> - 3.6.1-3
- Rename python3.Xdm-config script from -debug to be arch specific
Resolves: rhbz#1179073

* Wed Apr 05 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.1-2
- Install the Makefile in its proper location (rhbz#1438219)

* Wed Mar 22 2017 Iryna Shcherbina <ishcherb@redhat.com> - 3.6.1-1
- Update to version 3.6.1 final

* Tue Mar 21 2017 Tomas Orsava <torsava@redhat.com> - 3.6.1-0.2.rc1
- Fix syntax error in %%py_byte_compile macro (rhbz#1433569)

* Thu Mar 16 2017 Iryna Shcherbina <ishcherb@redaht.com> - 3.6.1-0.1.rc1
- Update to Python 3.6.1 release candidate 1
- Add patch 264 to skip a known test failure on aarch64

* Fri Mar 10 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.0-21
- Use proper command line parsing in _testembed
- Backport of PEP 538: Coercing the legacy C locale to a UTF-8 based locale
  https://fedoraproject.org/wiki/Changes/python3_c.utf-8_locale

* Mon Feb 27 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.0-20
- Add desktop entry and appdata.xml file for IDLE 3 (rhbz#1392049)

* Fri Feb 24 2017 Michal Cyprian <mcyprian@redhat.com> - 3.6.0-19
- Revert "Set values of prefix and exec_prefix to /usr/local for
  /usr/bin/python* executables..." to prevent build failures
  of packages using alternate build tools

* Tue Feb 21 2017 Michal Cyprian <mcyprian@redhat.com> - 3.6.0-18
- Set values of prefix and exec_prefix to /usr/local for
  /usr/bin/python* executables
- Use new %%_module_build macro

* Fri Feb 17 2017 Michal Cyprian <mcyprian@redhat.com> - 3.6.0-13
- Add --executable option to install.py command

* Wed Feb 15 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.0-12
- BuildRequire the new dependencies of setuptools when rewheel mode is enabled
in order for the virtualenvs to work properly

* Sat Feb 11 2017 Fedora Release Engineering <releng@fedoraproject.org> - 3.6.0-11
- Rebuilt for https://fedoraproject.org/wiki/Fedora_26_Mass_Rebuild

* Wed Feb 01 2017 Stephen Gallagher <sgallagh@redhat.com> - 3.6.0-10
- Add missing %%license macro

* Thu Jan 26 2017 Tomas Orsava <torsava@redhat.com> - 3.6.0-9
- Modify the runtime dependency of python3-libs on system-python-libs again,
  because previous attempt didn't work properly with dnf resolving mechanism

* Wed Jan 25 2017 Tomas Orsava <torsava@redhat.com> - 3.6.0-8
- Modify the runtime dependency of python3-libs on system-python-libs to use
  just the version and release number, but not the dist tag due to Modularity

* Mon Jan 16 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.0-7
- Fix error check, so that Random.seed actually uses OS randomness (rhbz#1412275)
- Skip test_aead_aes_gcm during rpmbuild

* Thu Jan 12 2017 Igor Gnatenko <ignatenko@redhat.com> - 3.6.0-6
- Rebuild for readline 7.x

* Tue Jan 10 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.0-5
- Require glibc >= 2.24.90-26 for system-python-libs (rhbz#1410644)

* Mon Jan 09 2017 Charalampos Stratakis <cstratak@redhat.com> - 3.6.0-4
- Define HAVE_LONG_LONG as 1 for backwards compatibility

* Thu Jan 05 2017 Miro Hrončok <mhroncok@redhat.com> - 3.6.0-3
- Don't blow up on EL7 kernel (random generator) (rhbz#1410175)

* Tue Dec 27 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.6.0-1
- Update to Python 3.6.0 final

* Fri Dec 09 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.6.0-0.6.rc1
- Enable rewheel

* Wed Dec 07 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.6.0-0.5.rc1
- Update to Python 3.6.0 release candidate 1

* Mon Dec 05 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.6.0-0.4.b4
- Update to Python 3.6.0 beta 4

* Mon Dec 05 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.5.2-7
- Set to work with pip version 9.0.1

* Wed Oct 12 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.5.2-6
- Use proper patch numbering and base upstream branch for
porting ssl and hashlib modules to OpenSSL 1.1.0
- Drop hashlib patch for now
- Add riscv64 arch to 64bit and no-valgrind arches

* Tue Oct 11 2016 Tomáš Mráz <tmraz@redhat.com> - 3.5.2-5
- Make it build with OpenSSL-1.1.0 based on upstream patch

* Wed Sep 14 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.5.2-4
- Obsolete and Provide python35 package

* Mon Sep 12 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.5.2-3
- Update %%py_byte_compile macro
- Remove unused configure flags (rhbz#1374357)

* Fri Sep 09 2016 Tomas Orsava <torsava@redhat.com> - 3.5.2-2
- Updated .pyc 'bytecompilation with the newly installed interpreter' to also
  recompile optimized .pyc files
- Removed .pyo 'bytecompilation with the newly installed interpreter', as .pyo
  files are no more
- Resolves rhbz#1373635

* Mon Aug 15 2016 Tomas Orsava <torsava@redhat.com> - 3.5.2-1
- Rebased to version 3.5.2
- Set to work with pip version 8.1.2
- Removed patches 207, 237, 241 as fixes are already contained in Python 3.5.2
- Removed arch or environment specific patches 194, 196, 203, and 208
  as test builds indicate they are no longer needed
- Updated patches 102, 146, and 242 to work with the new Python codebase
- Removed patches 200, 201, 5000 which weren't even being applied

* Tue Aug 09 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.5.1-15
- Fix for CVE-2016-1000110 HTTPoxy attack
- SPEC file cleanup

* Mon Aug 01 2016 Michal Toman <mtoman@fedoraproject.org> - 3.5.1-14
- Build properly on MIPS

* Tue Jul 19 2016 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 3.5.1-13
- https://fedoraproject.org/wiki/Changes/Automatic_Provides_for_Python_RPM_Packages

* Fri Jul 08 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.5.1-12
- Refactor patch for properly fixing CVE-2016-5636

* Fri Jul 08 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.5.1-11
- Fix test_pyexpat failure with Expat version of 2.2.0

* Fri Jul 08 2016 Miro Hrončok <mhroncok@redhat.com> - 3.5.1-10
- Move xml module to system-python-libs

* Thu Jun 16 2016 Tomas Orsava <torsava@redhat.com> - 3.5.1-9
- Fix for: CVE-2016-0772 python: smtplib StartTLS stripping attack
- Raise an error when STARTTLS fails
- rhbz#1303647: https://bugzilla.redhat.com/show_bug.cgi?id=1303647
- rhbz#1346345: https://bugzilla.redhat.com/show_bug.cgi?id=1346345
- Fixed upstream: https://hg.python.org/cpython/rev/d590114c2394

* Mon Jun 13 2016 Charalampos Stratakis <cstratak@redhat.com> - 3.5.1-8
- Added patch for fixing possible integer overflow and heap corruption in zipimporter.get_data()

* Fri Mar 04 2016 Miro Hrončok <mhroncok@redhat.com> - 3.5.1-7
- Move distutils to system-python-libs

* Wed Feb 24 2016 Robert Kuska <rkuska@redhat.com> - 3.5.1-6
- Provide python3-enum34

* Fri Feb 19 2016 Miro Hrončok <mhroncok@redhat.com> - 3.5.1-5
- Provide System Python packages and macros

* Thu Feb 04 2016 Fedora Release Engineering <releng@fedoraproject.org> - 3.5.1-4
- Rebuilt for https://fedoraproject.org/wiki/Fedora_24_Mass_Rebuild

* Wed Jan 13 2016 Orion Poplwski <orion@cora.nwra.com> - 3.5.1-2
- Drop python3 macros, require python/python3-rpm-macros

* Mon Dec 14 2015 Robert Kuska <rkuska@redhat.com> - 3.5.1-1
- Update to 3.5.1
- Removed patch 199 and 207 (upstream)

* Sun Nov 15 2015 Robert Kuska <rkuska@redhat.com> - 3.5.0-5
- Remove versioned libpython from devel package

* Fri Nov 13 2015 Than Ngo <than@redhat.com> 3.5.0-4
- add correct arch for ppc64/ppc64le to fix build failure

* Wed Nov 11 2015 Robert Kuska <rkuska@redhat.com> - 3.5.0-3
- Hide the private _Py_atomic_xxx symbols from public header

* Wed Oct 14 2015 Robert Kuska <rkuska@redhat.com> - 3.5.0-2
- Rebuild with wheel set to 1

* Tue Sep 15 2015 Matej Stuchlik <mstuchli@redhat.com> - 3.5.0-1
- Update to 3.5.0

* Mon Jun 29 2015 Thomas Spura <tomspur@fedoraproject.org> - 3.4.3-4
- python3-devel: Require python-macros for version independant macros such as
  python_provide. See fpc#281 and fpc#534.

* Thu Jun 18 2015 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 3.4.3-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_23_Mass_Rebuild

* Wed Jun 17 2015 Matej Stuchlik <mstuchli@redhat.com> - 3.4.3-4
- Use 1024bit DH key in test_ssl
- Use -O0 when compiling -debug build
- Update pip version variable to the version we actually ship

* Wed Jun 17 2015 Matej Stuchlik <mstuchli@redhat.com> - 3.4.3-3
- Make relocating Python by changing _prefix actually work
Resolves: rhbz#1231801

* Mon May  4 2015 Peter Robinson <pbrobinson@fedoraproject.org> 3.4.3-2
- Disable test_gdb on aarch64 (rhbz#1196181), it joins all other non x86 arches

* Thu Mar 12 2015 Matej Stuchlik <mstuchli@redhat.com> - 3.4.3-1
- Updated to 3.4.3
- BuildPython now accepts additional build options
- Temporarily disabled test_gdb on arm (rhbz#1196181)

* Wed Feb 25 2015 Matej Stuchlik <mstuchli@redhat.com> - 3.4.2-7
- Fixed undefined behaviour in faulthandler which caused test to hang on x86_64
  (http://bugs.python.org/issue23433)

* Sat Feb 21 2015 Till Maas <opensource@till.name> - 3.4.2-6
- Rebuilt for Fedora 23 Change
  https://fedoraproject.org/wiki/Changes/Harden_all_packages_with_position-independent_code

* Tue Feb 17 2015 Ville Skyttä <ville.skytta@iki.fi> - 3.4.2-5
- Own systemtap dirs (#710733)

* Mon Jan 12 2015 Dan Horák <dan[at]danny.cz> - 3.4.2-4
- build with valgrind on ppc64le
- disable test_gdb on s390(x) until rhbz#1181034 is resolved

* Tue Dec 16 2014 Robert Kuska <rkuska@redhat.com> - 3.4.2-3
- New patches: 170 (gc asserts), 200 (gettext headers),
  201 (gdbm memory leak)

* Thu Dec 11 2014 Robert Kuska <rkuska@redhat.com> - 3.4.2-2
- OpenSSL disabled SSLv3 in SSLv23 method

* Thu Nov 13 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.2-1
- Update to 3.4.2
- Refreshed patches: 156 (gdb autoload)
- Removed: 195 (Werror declaration), 197 (CVE-2014-4650)

* Mon Nov 03 2014 Slavek Kabrda <bkabrda@redhat.com> - 3.4.1-16
- Fix CVE-2014-4650 - CGIHTTPServer URL handling
Resolves: rhbz#1113529

* Sun Sep 07 2014 Karsten Hopp <karsten@redhat.com> 3.4.1-15
- exclude test_gdb on ppc* (rhbz#1132488)

* Thu Aug 21 2014 Slavek Kabrda <bkabrda@redhat.com> - 3.4.1-14
- Update rewheel patch with fix from https://github.com/bkabrda/rewheel/pull/1

* Sun Aug 17 2014 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 3.4.1-13
- Rebuilt for https://fedoraproject.org/wiki/Fedora_21_22_Mass_Rebuild

* Sun Jun  8 2014 Peter Robinson <pbrobinson@fedoraproject.org> 3.4.1-12
- aarch64 has valgrind, just list those that don't support it

* Sun Jun 08 2014 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 3.4.1-11
- Rebuilt for https://fedoraproject.org/wiki/Fedora_21_Mass_Rebuild

* Wed Jun 04 2014 Karsten Hopp <karsten@redhat.com> 3.4.1-10
- bump release and rebuild to link with the correct tcl/tk libs on ppcle

* Tue Jun 03 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.1-9
- Change paths to bundled projects in rewheel patch

* Fri May 30 2014 Miro Hrončok <mhroncok@redhat.com> - 3.4.1-8
- In config script, use uname -m to write the arch

* Thu May 29 2014 Dan Horák <dan[at]danny.cz> - 3.4.1-7
- update the arch list where valgrind exists - %%power64 includes also
    ppc64le which is not supported yet

* Thu May 29 2014 Miro Hrončok <mhroncok@redhat.com> - 3.4.1-6
- Forward arguments to the arch specific config script
Resolves: rhbz#1102683

* Wed May 28 2014 Miro Hrončok <mhroncok@redhat.com> - 3.4.1-5
- Rename python3.Xm-config script to arch specific.
Resolves: rhbz#1091815

* Tue May 27 2014 Bohuslav Kabrda <bkabrda@redhat.com> - 3.4.1-4
- Use python3-*, not python-* runtime requires on setuptools and pip
- rebuild for tcl-8.6

* Tue May 27 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.1-3
- Update the rewheel module

* Mon May 26 2014 Miro Hrončok <mhroncok@redhat.com> - 3.4.1-2
- Fix multilib dependencies.
Resolves: rhbz#1091815

* Sun May 25 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.1-1
- Update to Python 3.4.1

* Sun May 25 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.0-8
- Fix test_gdb failure on ppc64le
Resolves: rhbz#1095355

* Thu May 22 2014 Miro Hrončok <mhroncok@redhat.com> - 3.4.0-7
- Add macro %%python3_version_nodots

* Sun May 18 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.0-6
- Disable test_faulthandler, test_gdb on aarch64
Resolves: rhbz#1045193

* Fri May 16 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.0-5
- Don't add Werror=declaration-after-statement for extension
  modules through setup.py (PyBT#21121)

* Mon May 12 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.0-4
- Add setuptools and pip to Requires

* Tue Apr 29 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.0-3
- Point __os_install_post to correct brp-* files

* Tue Apr 15 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.0-2
- Temporarily disable tests requiring SIGHUP (rhbz#1088233)

* Tue Apr 15 2014 Matej Stuchlik <mstuchli@redhat.com> - 3.4.0-1
- Update to Python 3.4 final
- Add patch adding the rewheel module
- Merge patches from master

* Wed Jan 08 2014 Bohuslav Kabrda <bkabrda@redhat.com> - 3.4.0-0.1.b2
- Update to Python 3.4 beta 2.
- Refreshed patches: 55 (systemtap), 146 (hashlib-fips), 154 (test_gdb noise)
- Dropped patches: 114 (statvfs constants), 177 (platform unicode)

* Mon Nov 25 2013 Bohuslav Kabrda <bkabrda@redhat.com> - 3.4.0-0.1.b1
- Update to Python 3.4 beta 1.
- Refreshed patches: 102 (lib64), 111 (no static lib), 125 (less verbose COUNT
ALLOCS), 141 (fix COUNT_ALLOCS in test_module), 146 (hashlib fips),
157 (UID+GID overflows), 173 (ENOPROTOOPT in bind_port)
- Removed patch 00187 (remove pthread atfork; upstreamed)

* Mon Nov 04 2013 Bohuslav Kabrda <bkabrda@redhat.com> - 3.4.0-0.1.a4
- Update to Python 3.4 alpha 4.
- Refreshed patches: 55 (systemtap), 102 (lib64), 111 (no static lib),
114 (statvfs flags), 132 (unittest rpmbuild hooks), 134 (fix COUNT_ALLOCS in
test_sys), 143 (tsc on ppc64), 146 (hashlib fips), 153 (test gdb noise),
157 (UID+GID overflows), 173 (ENOPROTOOPT in bind_port), 186 (dont raise
from py_compile)
- Removed patches: 129 (test_subprocess nonreadable dir - no longer fails in
Koji), 142 (the mock issue that caused this is fixed)
- Added patch 187 (remove thread atfork) - will be in next version
- Refreshed script for checking pyc and pyo timestamps with new ignored files.
- The fips patch is disabled for now until upstream makes a final decision
what to do with sha3 implementation for 3.4.0.

* Wed Oct 30 2013 Bohuslav Kabrda <bkabrda@redhat.com> - 3.3.2-7
- Bytecompile all *.py files properly during build (rhbz#1023607)

* Fri Aug 23 2013 Matej Stuchlik <mstuchli@redhat.com> - 3.3.2-6
- Added fix for CVE-2013-4238 (rhbz#996399)

* Fri Jul 26 2013 Dennis Gilmore <dennis@ausil.us> - 3.3.2-5
- fix up indentation in arm patch

* Fri Jul 26 2013 Dennis Gilmore <dennis@ausil.us> - 3.3.2-4
- disable a test that fails on arm
- enable valgrind support on arm arches

* Tue Jul 02 2013 Bohuslav Kabrda <bkabrda@redhat.com> - 3.3.2-3
- Fix build with libffi containing multilib wrapper for ffi.h (rhbz#979696).

* Mon May 20 2013 Bohuslav Kabrda <bkabrda@redhat.com> - 3.3.2-2
- Add patch for CVE-2013-2099 (rhbz#963261).

* Thu May 16 2013 Bohuslav Kabrda <bkabrda@redhat.com> - 3.3.2-1
- Updated to Python 3.3.2.
- Refreshed patches: 153 (gdb test noise)
- Dropped patches: 175 (configure -Wformat, fixed upstream), 182 (gdb
test threads)
- Synced patch numbers with python.spec.

* Thu May  9 2013 David Malcolm <dmalcolm@redhat.com> - 3.3.1-4
- fix test.test_gdb.PyBtTests.test_threads on ppc64 (patch 181; rhbz#960010)

* Thu May 02 2013 Bohuslav Kabrda <bkabrda@redhat.com> - 3.3.1-3
- Add patch that enables building on ppc64p7 (replace the sed, so that
we get consistent with python2 spec and it's more obvious that we're doing it.

* Wed Apr 24 2013 Bohuslav Kabrda <bkabrda@redhat.com> - 3.3.1-2
- Add fix for gdb tests failing on arm, rhbz#951802.

* Tue Apr 09 2013 Bohuslav Kabrda <bkabrda@redhat.com> - 3.3.1-1
- Updated to Python 3.3.1.
- Refreshed patches: 55 (systemtap), 111 (no static lib), 146 (hashlib fips),
153 (fix test_gdb noise), 157 (uid, gid overflow - fixed upstream, just
keeping few more downstream tests)
- Removed patches: 3 (audiotest.au made it to upstream tarball)
- Removed workaround for http://bugs.python.org/issue14774, discussed in
http: //bugs.python.org/issue15298 and fixed in revision 24d52d3060e8.

* Mon Mar 25 2013 David Malcolm <dmalcolm@redhat.com> - 3.3.0-10
- fix gcc 4.8 incompatibility (rhbz#927358); regenerate autotool intermediates

* Mon Mar 25 2013 David Malcolm <dmalcolm@redhat.com> - 3.3.0-9
- renumber patches to keep them in sync with python.spec

* Fri Mar 15 2013 Toshio Kuratomi <toshio@fedoraproject.org> - 3.3.0-8
- Fix error in platform.platform() when non-ascii byte strings are decoded to
  unicode (rhbz#922149)

* Thu Mar 14 2013 Toshio Kuratomi <toshio@fedoraproject.org> - 3.3.0-7
- Fix up shared library extension (rhbz#889784)

* Thu Mar 07 2013 Karsten Hopp <karsten@redhat.com> 3.3.0-6
- add ppc64p7 build target, optimized for Power7

* Mon Mar  4 2013 David Malcolm <dmalcolm@redhat.com> - 3.3.0-5
- add workaround for ENOPROTOOPT seen running selftests in Koji
(rhbz#913732)

* Mon Mar  4 2013 David Malcolm <dmalcolm@redhat.com> - 3.3.0-4
- remove config flag from /etc/rpm/macros.{python3|pybytecompile}

* Mon Feb 11 2013 David Malcolm <dmalcolm@redhat.com> - 3.3.0-3
- add aarch64 (rhbz#909783)

* Thu Nov 29 2012 David Malcolm <dmalcolm@redhat.com> - 3.3.0-2
- add BR on bluez-libs-devel (rhbz#879720)

* Sat Sep 29 2012 David Malcolm <dmalcolm@redhat.com> - 3.3.0-1
- 3.3.0rc3 -> 3.3.0; drop alphatag

* Mon Sep 24 2012 David Malcolm <dmalcolm@redhat.com> - 3.3.0-0.6.rc3
- 3.3.0rc2 -> 3.3.0rc3

* Mon Sep 10 2012 David Malcolm <dmalcolm@redhat.com> - 3.3.0-0.5.rc2
- 3.3.0rc1 -> 3.3.0rc2; refresh patch 55

* Mon Aug 27 2012 David Malcolm <dmalcolm@redhat.com> - 3.3.0-0.4.rc1
- 3.3.0b2 -> 3.3.0rc1; refresh patches 3, 55

* Mon Aug 13 2012 David Malcolm <dmalcolm@redhat.com> - 3.3.0-0.3.b2
- 3.3b1 -> 3.3b2; drop upstreamed patch 152; refresh patches 3, 102, 111,
134, 153, 160; regenenerate autotools patch; rework systemtap patch to work
correctly when LANG=C (patch 55); importlib.test was moved to
test.test_importlib upstream

* Mon Aug 13 2012 Karsten Hopp <karsten@redhat.com> 3.3.0-0.2.b1
- disable some failing checks on PPC* (rhbz#846849)

* Fri Aug  3 2012 David Malcolm <dmalcolm@redhat.com> - 3.3.0-0.1.b1
- 3.2 -> 3.3: https://fedoraproject.org/wiki/Features/Python_3.3
- 3.3.0b1: refresh patches 3, 55, 102, 111, 113, 114, 134, 157; drop upstream
patch 147; regenenerate autotools patch; drop "--with-wide-unicode" from
configure (PEP 393); "plat-linux2" -> "plat-linux" (upstream issue 12326);
"bz2" -> "_bz2" and "crypt" -> "_crypt"; egg-info files are no longer shipped
for stdlib (upstream issues 10645 and 12218); email/test moved to
test/test_email; add /usr/bin/pyvenv[-3.3] and venv module (PEP 405); add
_decimal and _lzma modules; make collections modules explicit in payload again
(upstream issue 11085); add _testbuffer module to tests subpackage (added in
upstream commit 3f9b3b6f7ff0); fix test failures (patches 160 and 161);
workaround erroneously shared _sysconfigdata.py upstream issue #14774; fix
distutils.sysconfig traceback (patch 162); add BuildRequires: xz-devel (for
_lzma module); skip some tests within test_socket (patch 163)

* Sat Jul 21 2012 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 3.2.3-11
- Rebuilt for https://fedoraproject.org/wiki/Fedora_18_Mass_Rebuild

* Fri Jul 20 2012 David Malcolm <dmalcolm@redhat.com> - 3.3.0-0.1.b1

* Fri Jun 22 2012 David Malcolm <dmalcolm@redhat.com> - 3.2.3-10
- use macro for power64 (rhbz#834653)

* Mon Jun 18 2012 David Malcolm <dmalcolm@redhat.com> - 3.2.3-9
- fix missing include in uid/gid handling patch (patch 157; rhbz#830405)

* Wed May 30 2012 Bohuslav Kabrda <bkabrda@redhat.com> - 3.2.3-8
- fix tapset for debug build

* Tue May 15 2012 David Malcolm <dmalcolm@redhat.com> - 3.2.3-7
- update uid/gid handling to avoid int overflows seen with uid/gid
values >= 2^31 on 32-bit architectures (patch 157; rhbz#697470)

* Fri May  4 2012 David Malcolm <dmalcolm@redhat.com> - 3.2.3-6
- renumber autotools patch from 300 to 5000
- specfile cleanups

* Mon Apr 30 2012 David Malcolm <dmalcolm@redhat.com> - 3.2.3-5
- fix test_gdb.py (patch 156; rhbz#817072)

* Fri Apr 20 2012 David Malcolm <dmalcolm@redhat.com> - 3.2.3-4
- avoid allocating thunks in ctypes unless absolutely necessary, to avoid
generating SELinux denials on "import ctypes" and "import uuid" when embedding
Python within httpd (patch 155; rhbz#814391)

* Fri Apr 20 2012 David Malcolm <dmalcolm@redhat.com> - 3.2.3-3
- add explicit version requirements on expat to avoid linkage problems with
XML_SetHashSalt

* Thu Apr 12 2012 David Malcolm <dmalcolm@redhat.com> - 3.2.3-2
- fix test_gdb (patch 153)

* Wed Apr 11 2012 David Malcolm <dmalcolm@redhat.com> - 3.2.3-1
- 3.2.3; refresh patch 102 (lib64); drop upstream patches 148 (gdbm magic
values), 149 (__pycache__ fix); add patch 152 (test_gdb regex)

* Thu Feb  9 2012 Thomas Spura <tomspur@fedoraproject.org> - 3.2.2-13
- use newly installed python for byte compiling (now for real)

* Sun Feb  5 2012 Thomas Spura <tomspur@fedoraproject.org> - 3.2.2-12
- use newly installed python for byte compiling (#787498)

* Wed Jan  4 2012 Ville Skyttä <ville.skytta@iki.fi> - 3.2.2-11
- Build with $RPM_LD_FLAGS (#756863).
- Use xz-compressed source tarball.

* Wed Dec 07 2011 Karsten Hopp <karsten@redhat.com> 3.2.2-10
- disable rAssertAlmostEqual in test_cmath on PPC (#750811)

* Mon Oct 17 2011 Rex Dieter <rdieter@fedoraproject.org> - 3.2.2-9
- python3-devel missing autogenerated pkgconfig() provides (#746751)

* Mon Oct 10 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.2-8
- cherrypick fix for distutils not using __pycache__ when byte-compiling
files (rhbz#722578)

* Fri Sep 30 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.2-7
- re-enable gdbm (patch 148; rhbz#742242)

* Fri Sep 16 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.2-6
- add a sys._debugmallocstats() function (patch 147)

* Wed Sep 14 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.2-5
- support OpenSSL FIPS mode in _hashlib and hashlib; don't build the _md5 and
_sha* modules, relying on _hashlib in hashlib (rhbz#563986; patch 146)

* Tue Sep 13 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.2-4
- disable gdbm module to prepare for gdbm soname bump

* Mon Sep 12 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.2-3
- renumber and rename patches for consistency with python.spec (8 to 55, 106
to 104, 6 to 111, 104 to 113, 105 to 114, 125, 131, 130 to 143)

* Sat Sep 10 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.2-2
- rewrite of "check", introducing downstream-only hooks for skipping specific
cases in an rpmbuild (patch 132), and fixing/skipping failing tests in a more
fine-grained manner than before; (patches 106, 133-142 sparsely, moving
patches for consistency with python.spec: 128 to 134, 126 to 135, 127 to 141)

* Tue Sep  6 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.2-1
- 3.2.2

* Thu Sep  1 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.1-7
- run selftests with "--verbose"
- disable parts of test_io on ppc (rhbz#732998)

* Wed Aug 31 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.1-6
- use "--findleaks --verbose3" when running test suite

* Tue Aug 23 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.1-5
- re-enable and fix the --with-tsc option on ppc64, and rework it on 32-bit
ppc to avoid aliasing violations (patch 130; rhbz#698726)

* Tue Aug 23 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.1-4
- don't use --with-tsc on ppc64 debug builds (rhbz#698726)

* Thu Aug 18 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.1-3
- add %%python3_version to the rpm macros (rhbz#719082)

* Mon Jul 11 2011 Dennis Gilmore <dennis@ausil.us> - 3.2.1-2
- disable some tests on sparc arches

* Mon Jul 11 2011 David Malcolm <dmalcolm@redhat.com> - 3.2.1-1
- 3.2.1; refresh lib64 patch (102), subprocess unit test patch (129), disabling
of static library build (due to Modules/_testembed; patch 6), autotool
intermediates (patch 300)

* Fri Jul  8 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-5
- use the gdb hooks from the upstream tarball, rather than keeping our own copy

* Fri Jul  8 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-4
- don't run test_openpty and test_pty in %%check

* Fri Jul  8 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-3
- cleanup of BuildRequires; add comment headings to specfile sections

* Tue Apr 19 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-2
- fix the libpython.stp systemtap tapset (rhbz#697730)

* Mon Feb 21 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-1
- 3.2
- drop alphatag
- regenerate autotool patch

* Mon Feb 14 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-0.13.rc3
- add a /usr/bin/python3-debug symlink within the debug subpackage

* Mon Feb 14 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-0.12.rc3
- 3.2rc3
- regenerate autotool patch

* Wed Feb 09 2011 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 3.2-0.11.rc2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_15_Mass_Rebuild

* Mon Jan 31 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-0.10.rc2
- 3.2rc2

* Mon Jan 17 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-0.9.rc1
- 3.2rc1
- rework patch 6 (static lib removal)
- remove upstreamed patch 130 (ppc debug build)
- regenerate patch 300 (autotool intermediates)
- updated packaging to reflect upstream rewrite of "Demo" (issue 7962)
- added libpython3.so and 2to3-3.2

* Wed Jan  5 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-0.8.b2
- set EXTRA_CFLAGS to our CFLAGS, rather than overriding OPT, fixing a linker
error with dynamic annotations (when configured using --with-valgrind)
- fix the ppc build of the debug configuration (patch 130; rhbz#661510)

* Tue Jan  4 2011 David Malcolm <dmalcolm@redhat.com> - 3.2-0.7.b2
- add --with-valgrind to configuration (on architectures that support this)

* Wed Dec 29 2010 David Malcolm <dmalcolm@redhat.com> - 3.2-0.6.b2
- work around test_subprocess failure seen in koji (patch 129)

* Tue Dec 28 2010 David Malcolm <dmalcolm@redhat.com> - 3.2-0.5.b2
- 3.2b2
- rework patch 3 (removal of mimeaudio tests), patch 6 (no static libs),
patch 8 (systemtap), patch 102 (lib64)
- remove patch 4 (rendered redundant by upstream r85537), patch 103 (PEP 3149),
patch 110 (upstreamed expat fix), patch 111 (parallel build fix for grammar
fixed upstream)
- regenerate patch 300 (autotool intermediates)
- workaround COUNT_ALLOCS weakref issues in test suite (patch 126, patch 127,
patch 128)
- stop using runtest.sh in %%check (dropped by upstream), replacing with
regrtest; fixup list of failing tests
- introduce "pyshortver", "SOABI_optimized" and "SOABI_debug" macros
- rework manifests of shared libraries to use "SOABI_" macros, reflecting
PEP 3149
- drop itertools, operator and _collections modules from the manifests as py3k
commit r84058 moved these inside libpython; json/tests moved to test/json_tests
- move turtle code into the tkinter subpackage

* Wed Nov 17 2010 David Malcolm <dmalcolm@redhat.com> - 3.2-0.5.a1
- fix sysconfig to not rely on the -devel subpackage (rhbz#653058)

* Thu Sep  9 2010 David Malcolm <dmalcolm@redhat.com> - 3.2-0.4.a1
- move most of the content of the core package to the libs subpackage, given
that the libs aren't meaningfully usable without the standard libraries

* Wed Sep  8 2010 David Malcolm <dmalcolm@redhat.com> - 3.2-0.3.a1
- Move test.support to core package (rhbz#596258)
- Add various missing __pycache__ directories to payload

* Sun Aug 22 2010 Toshio Kuratomi <toshio@fedoraproject.org> - 3.2-0.2.a1
- Add __pycache__ directory for site-packages

* Sun Aug 22 2010 Thomas Spura <tomspur@fedoraproject.org> - 3.2-0.1.a1
- on 64bit "stdlib" was still "/usr/lib/python*" (modify *lib64.patch)
- make find-provides-without-python-sonames.sh 64bit aware

* Sat Aug 21 2010 David Malcolm <dmalcolm@redhat.com> - 3.2-0.0.a1
- 3.2a1; add alphatag
- rework %%files in the light of PEP 3147 (__pycache__)
- drop our configuration patch to Setup.dist (patch 0): setup.py should do a
better job of things, and the %%files explicitly lists our modules (r82746
appears to break the old way of doing things).  This leads to various modules
changing from "foomodule.so" to "foo.so".  It also leads to the optimized build
dropping the _sha1, _sha256 and _sha512 modules, but these are provided by
_hashlib; _weakref becomes a builtin module; xxsubtype goes away (it's only for
testing/devel purposes)
- fixup patches 3, 4, 6, 8, 102, 103, 105, 111 for the rebase
- remove upstream patches: 7 (system expat), 106, 107, 108 (audioop reformat
plus CVE-2010-1634 and CVE-2010-2089), 109 (CVE-2008-5983)
- add machinery for rebuilding "configure" and friends, using the correct
version of autoconf (patch 300)
- patch the debug build's usage of COUNT_ALLOCS to be less verbose (patch 125)
- "modulator" was removed upstream
- drop "-b" from patch applications affecting .py files to avoid littering the
installation tree

* Thu Aug 19 2010 Toshio Kuratomi <toshio@fedoraproject.org> - 3.1.2-13
- Turn on computed-gotos.
- Fix for parallel make and graminit.c

* Fri Jul  2 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-12
- rebuild

* Fri Jul  2 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-11
- Fix an incompatibility between pyexpat and the system expat-2.0.1 that led to
a segfault running test_pyexpat.py (patch 110; upstream issue 9054; rhbz#610312)

* Fri Jun  4 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-10
- ensure that the compiler is invoked with "-fwrapv" (rhbz#594819)
- reformat whitespace in audioop.c (patch 106)
- CVE-2010-1634: fix various integer overflow checks in the audioop
module (patch 107)
- CVE-2010-2089: further checks within the audioop module (patch 108)
- CVE-2008-5983: the new PySys_SetArgvEx entry point from r81399 (patch 109)

* Thu May 27 2010 Dan Horák <dan[at]danny.cz> - 3.1.2-9
- reading the timestamp counter is available only on some arches (see Python/ceval.c)

* Wed May 26 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-8
- add flags for statvfs.f_flag to the constant list in posixmodule (i.e. "os")
(patch 105)

* Tue May 25 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-7
- add configure-time support for COUNT_ALLOCS and CALL_PROFILE debug options
(patch 104); enable them and the WITH_TSC option within the debug build

* Mon May 24 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-6
- build and install two different configurations of Python 3: debug and
standard, packaging the debug build in a new "python3-debug" subpackage
(patch 103)

* Tue Apr 13 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-5
- exclude test_http_cookies when running selftests, due to hang seen on
http: //koji.fedoraproject.org/koji/taskinfo?taskID=2088463 (cancelled after
11 hours)
- update python-gdb.py from v5 to py3k version submitted upstream

* Wed Mar 31 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-4
- update python-gdb.py from v4 to v5 (improving performance and stability,
adding commands)

* Thu Mar 25 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-3
- update python-gdb.py from v3 to v4 (fixing infinite recursion on reference
cycles and tracebacks on bytes 0x80-0xff in strings, adding handlers for sets
and exceptions)

* Wed Mar 24 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-2
- refresh gdb hooks to v3 (reworking how they are packaged)

* Sun Mar 21 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.2-1
- update to 3.1.2: http://www.python.org/download/releases/3.1.2/
- drop upstreamed patch 2 (.pyc permissions handling)
- drop upstream patch 5 (fix for the test_tk and test_ttk_* selftests)
- drop upstreamed patch 200 (path-fixing script)

* Sat Mar 20 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-28
- fix typo in libpython.stp (rhbz:575336)

* Fri Mar 12 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-27
- add pyfuntop.stp example (source 7)
- convert usage of $$RPM_BUILD_ROOT to %%{buildroot} throughout, for
consistency with python.spec

* Mon Feb 15 2010 Thomas Spura <tomspur@fedoraproject.org> - 3.1.1-26
- rebuild for new package of redhat-rpm-config (rhbz:564527)
- use 'install -p' when running 'make install'

* Fri Feb 12 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-25
- split configure options into multiple lines for easy of editing
- add systemtap static markers (wcohen, mjw, dmalcolm; patch 8), a systemtap
tapset defining "python.function.entry" and "python.function.return" to make
the markers easy to use (dmalcolm; source 5), and an example of using the
tapset to the docs (dmalcolm; source 6) (rhbz:545179)

* Mon Feb  8 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-24
- move the -gdb.py file from %%{_libdir}/INSTSONAME-gdb.py to
%%{_prefix}/lib/debug/%%{_libdir}/INSTSONAME.debug-gdb.py to avoid noise from
ldconfig (bug 562980), and which should also ensure it becomes part of the
debuginfo subpackage, rather than the libs subpackage
- introduce %%{py_SOVERSION} and %%{py_INSTSONAME} to reflect the upstream
configure script, and to avoid fragile scripts that try to figure this out
dynamically (e.g. for the -gdb.py change)

* Mon Feb  8 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-23
- add gdb hooks for easier debugging (Source 4)

* Thu Jan 28 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-22
- update python-3.1.1-config.patch to remove downstream customization of build
of pyexpat and elementtree modules
- add patch adapted from upstream (patch 7) to add support for building against
system expat; add --with-system-expat to "configure" invocation
- remove embedded copies of expat and zlib from source tree during "prep"

* Mon Jan 25 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-21
- introduce %%{dynload_dir} macro
- explicitly list all lib-dynload files, rather than dynamically gathering the
payload into a temporary text file, so that we can be sure what we are
shipping
- introduce a macros.pybytecompile source file, to help with packaging python3
modules (Source3; written by Toshio)
- rename "2to3-3" to "python3-2to3" to better reflect python 3 module packaging
plans

* Mon Jan 25 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-20
- change python-3.1.1-config.patch to remove our downstream change to curses
configuration in Modules/Setup.dist, so that the curses modules are built using
setup.py with the downstream default (linking against libncursesw.so, rather
than libncurses.so), rather than within the Makefile; add a test to %%install
to verify the dso files that the curses module is linked against the correct
DSO (bug 539917; changes _cursesmodule.so -> _curses.so)

* Fri Jan 22 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-19
- add %%py3dir macro to macros.python3 (to be used during unified python 2/3
builds for setting up the python3 copy of the source tree)

* Wed Jan 20 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-18
- move lib2to3 from -tools subpackage to main package (bug 556667)

* Sun Jan 17 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-17
- patch Makefile.pre.in to avoid building static library (patch 6, bug 556092)

* Fri Jan 15 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-16
- use the %%{_isa} macro to ensure that the python-devel dependency on python
is for the correct multilib arch (#555943)
- delete bundled copy of libffi to make sure we use the system one

* Fri Jan 15 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-15
- fix the URLs output by pydoc so they point at python.org's 3.1 build of the
docs, rather than the 2.6 build

* Wed Jan 13 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-14
- replace references to /usr with %%{_prefix}; replace references to
/usr/include with %%{_includedir} (Toshio)

* Mon Jan 11 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-13
- fix permission on find-provides-without-python-sonames.sh from 775 to 755

* Mon Jan 11 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-12
- remove build-time requirements on tix and tk, since we already have
build-time requirements on the -devel subpackages for each of these (Thomas
Spura)
- replace usage of %%define with %%global (Thomas Spura)
- remove forcing of CC=gcc as this old workaround for bug 109268 appears to
longer be necessary
- move various test files from the "tools"/"tkinter" subpackages to the "test"
subpackage

* Thu Jan  7 2010 David Malcolm <dmalcolm@redhat.com> - 3.1.1-11
- add %%check section (thanks to Thomas Spura)
- update patch 4 to use correct shebang line
- get rid of stray patch file from buildroot

* Tue Nov 17 2009 Andrew McNabb <amcnabb@mcnabbs.org> - 3.1.1-10
- switched a few instances of "find |xargs" to "find -exec" for consistency.
- made the description of __os_install_post more accurate.

* Wed Nov  4 2009 David Malcolm <dmalcolm@redhat.com> - 3.1.1-9
- add macros.python3 to the -devel subpackage, containing common macros for use
when packaging python3 modules

* Tue Nov  3 2009 David Malcolm <dmalcolm@redhat.com> - 3.1.1-8
- add a provides of "python(abi)" (see bug 532118)
- fix issues identified by a.badger in package review (bug 526126, comment 39):
  - use "3" thoughout metadata, rather than "3.*"
  - remove conditional around "pkg-config openssl"
  - use standard cleanup of RPM_BUILD_ROOT
  - replace hardcoded references to /usr with _prefix macro
  - stop removing egg-info files
  - use /usr/bin/python3.1 rather than /use/bin/env python3.1 when fixing
up shebang lines
  - stop attempting to remove no-longer-present .cvsignore files
  - move the post/postun sections above the "files" sections

* Thu Oct 29 2009 David Malcolm <dmalcolm@redhat.com> - 3.1.1-7
- remove commented-away patch 51 (python-2.6-distutils_rpm.patch): the -O1
flag is used by default in the upstream code
- "Makefile" and the config-32/64.h file are needed by distutils/sysconfig.py
_init_posix(), so we include them in the core package, along with their parent
directories (bug 531901)

* Tue Oct 27 2009 David Malcolm <dmalcolm@redhat.com> - 3.1.1-6
- reword description, based on suggestion by amcnabb
- fix the test_email and test_imp selftests (patch 3 and patch 4 respectively)
- fix the test_tk and test_ttk_* selftests (patch 5)
- fix up the specfile's handling of shebang/perms to avoid corrupting
test_httpservers.py (sed command suggested by amcnabb)

* Thu Oct 22 2009 David Malcolm <dmalcolm@redhat.com> - 3.1.1-5
- fixup importlib/_bootstrap.py so that it correctly handles being unable to
open .pyc files for writing (patch 2, upstream issue 7187)
- actually apply the rpath patch (patch 1)

* Thu Oct 22 2009 David Malcolm <dmalcolm@redhat.com> - 3.1.1-4
- update patch0's setup of the crypt module to link it against libcrypt
- update patch0 to comment "datetimemodule" back out, so that it is built
using setup.py (see Setup, option 3), thus linking it statically against
timemodule.c and thus avoiding a run-time "undefined symbol:
_PyTime_DoubleToTimet" failure on "import datetime"

* Wed Oct 21 2009 David Malcolm <dmalcolm@redhat.com> - 3.1.1-3
- remove executable flag from various files that shouldn't have it
- fix end-of-line encodings
- fix a character encoding

* Tue Oct 20 2009 David Malcolm <dmalcolm@redhat.com> - 3.1.1-2
- disable invocation of brp-python-bytecompile in postprocessing, since
it would be with the wrong version of python (adapted from ivazquez'
python3000 specfile)
- use a custom implementation of __find_provides in order to filter out bogus
provides lines for the various .so modules
- fixup distutils/unixccompiler.py to remove standard library path from rpath
(patch 1, was Patch0 in ivazquez' python3000 specfile)
- split out libraries into a -libs subpackage
- update summaries and descriptions, basing content on ivazquez' specfile
- fixup executable permissions on .py, .xpm and .xbm files, based on work in
ivazquez's specfile
- get rid of DOS batch files
- fixup permissions for shared libraries from non-standard 555 to standard 755
- move /usr/bin/python*-config to the -devel subpackage
- mark various directories as being documentation

* Thu Sep 24 2009 Andrew McNabb <amcnabb@mcnabbs.org> 3.1.1-1
- Initial package for Python 3.

