#! /bin/bash -ex

# Download a release of Python (if missing) and remove .exe files from it

version=$1

if [ -z "${version}" ]; then
    echo "Usage: $0 VERSION" >& 2
    echo "" >& 2
    echo "example: $0 3.6.6" >& 2
    exit 1
fi

versionedname=Python-${version}
orig_archive=${versionedname}.tar.xz
new_archive=${versionedname}-noexe.tar.xz

if [ ! -e ${orig_archive} ]; then
    wget -N https://www.python.org/ftp/python/${version}/${orig_archive}
fi

deleted_names=$(tar --list -Jf ${orig_archive} | grep '\.exe$')

# tar --delete does not operate on compressed archives, so do
# xz compression/decompression explicitly
xz --decompress --stdout ${orig_archive} | \
    tar --delete -v ${deleted_names} | \
    xz --compress --stdout -3 -T0 > ${new_archive}
