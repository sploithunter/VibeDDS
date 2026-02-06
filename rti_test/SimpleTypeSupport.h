
/*
WARNING: THIS FILE IS AUTO-GENERATED. DO NOT MODIFY.

This file was generated from SimpleType.idl
using RTI Code Generator (rtiddsgen) version 4.3.0.5.
The rtiddsgen tool is part of the RTI Connext DDS distribution.
For more information, type 'rtiddsgen -help' at a command shell
or consult the Code Generator User's Manual.
*/

#ifndef SimpleTypeSupport_489918098_h
#define SimpleTypeSupport_489918098_h

/* Uses */
#include "SimpleType.h"

#ifndef ndds_c_h
#include "ndds/ndds_c.h"
#endif

#ifdef __cplusplus
extern "C" {
    #endif

    #if (defined(RTI_WIN32) || defined (RTI_WINCE) || defined(RTI_INTIME)) && defined(NDDS_USER_DLL_EXPORT)

    #endif

    /* ========================================================================= */
    /**
    Uses:     T

    Defines:  TTypeSupport, TDataWriter, TDataReader

    Organized using the well-documented "Generics Pattern" for
    implementing generics in C and C++.
    */

    #if (defined(RTI_WIN32) || defined (RTI_WINCE) || defined(RTI_INTIME)) && defined(NDDS_USER_DLL_EXPORT)
    /* If the code is building on Windows, start exporting symbols.
    */
    #undef NDDSUSERDllExport
    #define NDDSUSERDllExport __declspec(dllexport)

    #endif

    DDS_TYPESUPPORT_C(SimpleTypeTypeSupport, SimpleType);
    DDS_DATAWRITER_WITH_DATA_CONSTRUCTOR_METHODS_C(SimpleTypeDataWriter, SimpleType);
    DDS_DATAREADER_C(SimpleTypeDataReader, SimpleTypeSeq, SimpleType);

    #if (defined(RTI_WIN32) || defined (RTI_WINCE) || defined(RTI_INTIME)) && defined(NDDS_USER_DLL_EXPORT)
    /* If the code is building on Windows, stop exporting symbols.
    */
    #undef NDDSUSERDllExport
    #define NDDSUSERDllExport
    #endif

    #ifdef __cplusplus
}
#endif

#endif  /* SimpleTypeSupport_489918098_h */

