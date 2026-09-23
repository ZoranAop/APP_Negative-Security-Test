@echo off
REM ??: apksigner_verify.bat ^<APK^>
REM ?????? + ?????
set BT=C:\Users\zoran\AppData\Local\Temp\opencode\negtest\tools\build-tools\android-14
set JAVA_HOME=C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot
set PATH=%JAVA_HOME%\bin;%BT%;%PATH%
"%JAVA_HOME%\bin\java.exe" -jar "%BT%\lib\apksigner.jar" verify --verbose --print-certs %*
