[app]

title = DesignAssetIndexer
project_dir = ../..
input_file = launcher.py
project_file =
exec_directory = .build/deploy
icon =

[python]

python_path = ../../.venv-package-v030/Scripts/python.exe
packages = Nuitka==4.1.1
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]

qml_files =
excluded_qml_plugins = QtQuick,QtQuick3D,QtCharts,QtWebEngine,QtTest,QtSensors
modules = Core,Gui,Widgets
plugins = platforms,styles,imageformats,iconengines

[android]

wheel_pyside =
wheel_shiboken =
plugins =

[nuitka]

macos.permissions =
mode = standalone
extra_args = --quiet --noinclude-qt-translations --windows-console-mode=disable --output-filename=DesignAssetIndexer.exe --product-name=Design Asset Indexer --product-version=0.3.0 --file-version=0.3.0.0 --assume-yes-for-downloads --report=.build/nuitka-compilation-report.xml

[buildozer]

mode = debug
recipe_dir =
ndk_path =
sdk_path =
local_libs =
arch =
