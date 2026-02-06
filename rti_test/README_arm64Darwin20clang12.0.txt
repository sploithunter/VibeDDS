Welcome to your first Connext DDS example! 

This example was generated for architecture arm64Darwin20clang12.0, using the
data type SimpleType from SimpleType.idl.
This example builds two applications, named SimpleType_publisher and
SimpleType_subscriber.

To Build this example:
======================
 
From your command shell, type:
> make -f makefile_SimpleType_arm64Darwin20clang12.0
This command will build a release executable.
 
To build a debug version instead:
> make -f makefile_SimpleType_arm64Darwin20clang12.0 DEBUG=1

To Modify the Data:
===================
To modify the data being sent, edit the SimpleType_publisher.c
file where it says:
/* Modify the instance to be written here */

To Run this Example:
====================
Make sure you are in the directory where the USER_QOS_PROFILES.xml file was
generated (the same directory this README file is in).
Run /Applications/rti_connext_dds-7.3.0/resource/scripts/rtisetenv_arm64Darwin20clang12.0.bash
to make sure the Connext libraries are in the path, especially if you opened
a new command prompt window.
Run the publishing or subscribing application by typing:
> objs/arm64Darwin20clang12.0/SimpleType_publisher <domain_id> <sample_count>
> objs/arm64Darwin20clang12.0/SimpleType_subscriber <domain_id> <sample_count>
