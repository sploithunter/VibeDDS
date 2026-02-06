

/*
WARNING: THIS FILE IS AUTO-GENERATED. DO NOT MODIFY.

This file was generated from SimpleType.idl
using RTI Code Generator (rtiddsgen) version 4.3.0.5.
The rtiddsgen tool is part of the RTI Connext DDS distribution.
For more information, type 'rtiddsgen -help' at a command shell
or consult the Code Generator User's Manual.
*/

#ifndef SimpleType_489918098_h
#define SimpleType_489918098_h

#ifndef NDDS_STANDALONE_TYPE
#ifndef ndds_c_h
#include "ndds/ndds_c.h"
#endif
#else
#include "ndds_standalone_type.h"
#endif

#ifdef __cplusplus
extern "C" {
    #endif

    extern const char *SimpleTypeTYPENAME;

    typedef struct SimpleType
    {

        DDS_Char * message;
        DDS_Long x;
        DDS_Long y;
        DDS_Long count;

    } SimpleType ;
    #if (defined(RTI_WIN32) || defined (RTI_WINCE) || defined(RTI_INTIME)) && defined(NDDS_USER_DLL_EXPORT)
    /* If the code is building on Windows, start exporting symbols.
    */
    #undef NDDSUSERDllExport
    #define NDDSUSERDllExport __declspec(dllexport)
    #endif

    #ifndef NDDS_STANDALONE_TYPE
    NDDSUSERDllExport DDS_TypeCode * SimpleType_get_typecode(void); /* Type code */
    NDDSUSERDllExport RTIXCdrTypePlugin *SimpleType_get_type_plugin_info(void);
    NDDSUSERDllExport RTIXCdrSampleAccessInfo *SimpleType_get_sample_access_info(void);
    #endif
    DDS_SEQUENCE(SimpleTypeSeq, SimpleType);

    NDDSUSERDllExport
    RTIBool SimpleType_initialize(
        SimpleType* self);

    NDDSUSERDllExport
    RTIBool SimpleType_initialize_ex(
        SimpleType* self,RTIBool allocatePointers,RTIBool allocateMemory);

    NDDSUSERDllExport
    RTIBool SimpleType_initialize_w_params(
        SimpleType* self,
        const struct DDS_TypeAllocationParams_t * allocParams);  

    NDDSUSERDllExport
    RTIBool SimpleType_finalize_w_return(
        SimpleType* self);

    NDDSUSERDllExport
    void SimpleType_finalize(
        SimpleType* self);

    NDDSUSERDllExport
    void SimpleType_finalize_ex(
        SimpleType* self,RTIBool deletePointers);

    NDDSUSERDllExport
    void SimpleType_finalize_w_params(
        SimpleType* self,
        const struct DDS_TypeDeallocationParams_t * deallocParams);

    NDDSUSERDllExport
    void SimpleType_finalize_optional_members(
        SimpleType* self, RTIBool deletePointers);  

    NDDSUSERDllExport
    RTIBool SimpleType_copy(
        SimpleType* dst,
        const SimpleType* src);

    #if (defined(RTI_WIN32) || defined (RTI_WINCE) || defined(RTI_INTIME)) && defined(NDDS_USER_DLL_EXPORT)
    /* If the code is building on Windows, stop exporting symbols.
    */
    #undef NDDSUSERDllExport
    #define NDDSUSERDllExport
    #endif

    #ifdef __cplusplus
}
#endif

#endif /* SimpleType */

