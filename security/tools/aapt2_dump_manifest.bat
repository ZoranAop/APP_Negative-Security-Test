@echo off
REM ??: aapt2_dump_manifest.bat ^<APK^> [OUT_XML]
REM ?? aapt2 dump xmltree?? NS-02/03/14 ????
set BT=C:\Users\zoran\AppData\Local\Temp\opencode\negtest\tools\build-tools\android-14
set JAVA_HOME=C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot
set PATH=%JAVA_HOME%\bin;%BT%;%PATH%
"%BT%\aapt2.exe" dump xmltree %*
