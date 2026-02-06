

/*
WARNING: THIS FILE IS AUTO-GENERATED. DO NOT MODIFY.

This file was generated from SimpleType.idl
using RTI Code Generator (rtiddsgen) version 4.3.0.5.
The rtiddsgen tool is part of the RTI Connext DDS distribution.
For more information, type 'rtiddsgen -help' at a command shell
or consult the Code Generator User's Manual.
*/

#ifndef SimpleTypePlugin_489918098_h
#define SimpleTypePlugin_489918098_h

#include "SimpleType.h"

struct RTICdrStream;

#ifndef pres_typePlugin_h
#include "pres/pres_typePlugin.h"
#endif

#if (defined(RTI_WIN32) || defined (RTI_WINCE) || defined(RTI_INTIME)) && defined(NDDS_USER_DLL_EXPORT)
/* If the code is building on Windows, start exporting symbols.
*/
#undef NDDSUSERDllExport
#define NDDSUSERDllExport __declspec(dllexport)
#endif

#ifdef __cplusplus
extern "C" {
    #endif

    /* The type used to store keys for instances of type struct
    * AnotherSimple.
    *
    * By default, this type is struct SimpleType
    * itself. However, if for some reason this choice is not practical for your
    * system (e.g. if sizeof(struct SimpleType)
    * is very large), you may redefine this typedef in terms of another type of
    * your choosing. HOWEVER, if you define the KeyHolder type to be something
    * other than struct AnotherSimple, the
    * following restriction applies: the key of struct
    * SimpleType must consist of a
    * single field of your redefined KeyHolder type and that field must be the
    * first field in struct SimpleType.
    */
    typedef  struct SimpleType SimpleTypeKeyHolder;

    #define SimpleTypePlugin_get_sample PRESTypePluginDefaultEndpointData_getSample 

    #define SimpleTypePlugin_get_buffer PRESTypePluginDefaultEndpointData_getBuffer 
    #define SimpleTypePlugin_return_buffer PRESTypePluginDefaultEndpointData_returnBuffer

    #define SimpleTypePlugin_get_key PRESTypePluginDefaultEndpointData_getKey 
    #define SimpleTypePlugin_return_key PRESTypePluginDefaultEndpointData_returnKey

    #define SimpleTypePlugin_create_sample PRESTypePluginDefaultEndpointData_createSample 
    #define SimpleTypePlugin_destroy_sample PRESTypePluginDefaultEndpointData_deleteSample 

    /* --------------------------------------------------------------------------------------
    Support functions:
    * -------------------------------------------------------------------------------------- */

    NDDSUSERDllExport extern SimpleType*
    SimpleTypePluginSupport_create_data_w_params(
        const struct DDS_TypeAllocationParams_t * alloc_params);

    NDDSUSERDllExport extern SimpleType*
    SimpleTypePluginSupport_create_data_ex(RTIBool allocate_pointers);

    NDDSUSERDllExport extern SimpleType*
    SimpleTypePluginSupport_create_data(void);

    NDDSUSERDllExport extern RTIBool 
    SimpleTypePluginSupport_copy_data(
        SimpleType *out,
        const SimpleType *in);

    NDDSUSERDllExport extern void 
    SimpleTypePluginSupport_destroy_data_w_params(
        SimpleType *sample,
        const struct DDS_TypeDeallocationParams_t * dealloc_params);

    NDDSUSERDllExport extern void 
    SimpleTypePluginSupport_destroy_data_ex(
        SimpleType *sample,RTIBool deallocate_pointers);

    NDDSUSERDllExport extern void 
    SimpleTypePluginSupport_destroy_data(
        SimpleType *sample);

    NDDSUSERDllExport extern void 
    SimpleTypePluginSupport_print_data(
        const SimpleType *sample,
        const char *desc,
        unsigned int indent);

    NDDSUSERDllExport extern SimpleType*
    SimpleTypePluginSupport_create_key_ex(RTIBool allocate_pointers);

    NDDSUSERDllExport extern SimpleType*
    SimpleTypePluginSupport_create_key(void);

    NDDSUSERDllExport extern void 
    SimpleTypePluginSupport_destroy_key_ex(
        SimpleTypeKeyHolder *key,RTIBool deallocate_pointers);

    NDDSUSERDllExport extern void 
    SimpleTypePluginSupport_destroy_key(
        SimpleTypeKeyHolder *key);

    /* ----------------------------------------------------------------------------
    Callback functions:
    * ---------------------------------------------------------------------------- */

    NDDSUSERDllExport extern PRESTypePluginParticipantData 
    SimpleTypePlugin_on_participant_attached(
        void *registration_data, 
        const struct PRESTypePluginParticipantInfo *participant_info,
        RTIBool top_level_registration, 
        void *container_plugin_context,
        RTICdrTypeCode *typeCode);

    NDDSUSERDllExport extern void 
    SimpleTypePlugin_on_participant_detached(
        PRESTypePluginParticipantData participant_data);

    NDDSUSERDllExport extern PRESTypePluginEndpointData 
    SimpleTypePlugin_on_endpoint_attached(
        PRESTypePluginParticipantData participant_data,
        const struct PRESTypePluginEndpointInfo *endpoint_info,
        RTIBool top_level_registration, 
        void *container_plugin_context);

    NDDSUSERDllExport extern void 
    SimpleTypePlugin_on_endpoint_detached(
        PRESTypePluginEndpointData endpoint_data);

    NDDSUSERDllExport extern void    
    SimpleTypePlugin_return_sample(
        PRESTypePluginEndpointData endpoint_data,
        SimpleType *sample,
        void *handle);    

    NDDSUSERDllExport extern RTIBool 
    SimpleTypePlugin_copy_sample(
        PRESTypePluginEndpointData endpoint_data,
        SimpleType *out,
        const SimpleType *in);

    /* ----------------------------------------------------------------------------
    (De)Serialize functions:
    * ------------------------------------------------------------------------- */

    NDDSUSERDllExport extern RTIBool
    SimpleTypePlugin_serialize_to_cdr_buffer(
        char * buffer,
        unsigned int * length,
        const SimpleType *sample); 

    NDDSUSERDllExport extern RTIBool
    SimpleTypePlugin_serialize_to_cdr_buffer_ex(
        char *buffer,
        unsigned int *length,
        const SimpleType *sample,
        DDS_DataRepresentationId_t representation);

    NDDSUSERDllExport extern RTIBool
    SimpleTypePlugin_deserialize_from_cdr_buffer(
        SimpleType *sample,
        const char * buffer,
        unsigned int length);    
    #if !defined (NDDS_STANDALONE_TYPE)
    NDDSUSERDllExport extern DDS_ReturnCode_t
    SimpleTypePlugin_data_to_string(
        const SimpleType *sample,
        char *str,
        DDS_UnsignedLong *str_size, 
        const struct DDS_PrintFormatProperty *property);    
    #endif

    NDDSUSERDllExport extern unsigned int 
    SimpleTypePlugin_get_serialized_sample_max_size(
        PRESTypePluginEndpointData endpoint_data,
        RTIBool include_encapsulation,
        RTIEncapsulationId encapsulation_id,
        unsigned int current_alignment);

    /* --------------------------------------------------------------------------------------
    Key Management functions:
    * -------------------------------------------------------------------------------------- */
    NDDSUSERDllExport extern PRESTypePluginKeyKind 
    SimpleTypePlugin_get_key_kind(void);

    NDDSUSERDllExport extern unsigned int 
    SimpleTypePlugin_get_serialized_key_max_size(
        PRESTypePluginEndpointData endpoint_data,
        RTIBool include_encapsulation,
        RTIEncapsulationId encapsulation_id,
        unsigned int current_alignment);

    NDDSUSERDllExport extern unsigned int 
    SimpleTypePlugin_get_serialized_key_max_size_for_keyhash(
        PRESTypePluginEndpointData endpoint_data,
        RTIEncapsulationId encapsulation_id,
        unsigned int current_alignment);

    NDDSUSERDllExport extern RTIBool 
    SimpleTypePlugin_deserialize_key(
        PRESTypePluginEndpointData endpoint_data,
        SimpleType ** sample,
        RTIBool * drop_sample,
        struct RTICdrStream *cdrStream,
        RTIBool deserialize_encapsulation,
        RTIBool deserialize_key,
        void *endpoint_plugin_qos);

    NDDSUSERDllExport extern RTIBool 
    SimpleTypePlugin_instance_to_key(
        PRESTypePluginEndpointData endpoint_data,
        SimpleTypeKeyHolder *key, 
        const SimpleType *instance);

    NDDSUSERDllExport extern RTIBool 
    SimpleTypePlugin_key_to_instance(
        PRESTypePluginEndpointData endpoint_data,
        SimpleType *instance, 
        const SimpleTypeKeyHolder *key);

    NDDSUSERDllExport extern RTIBool 
    SimpleTypePlugin_serialized_sample_to_keyhash(
        PRESTypePluginEndpointData endpoint_data,
        struct RTICdrStream *cdrStream, 
        DDS_KeyHash_t *keyhash,
        RTIBool deserialize_encapsulation,
        void *endpoint_plugin_qos); 

    NDDSUSERDllExport extern
    struct RTIXCdrInterpreterPrograms * SimpleTypePlugin_get_programs(void);

    /* Plugin Functions */
    NDDSUSERDllExport extern struct PRESTypePlugin*
    SimpleTypePlugin_new(void);

    NDDSUSERDllExport extern void
    SimpleTypePlugin_delete(struct PRESTypePlugin *);

    #ifdef __cplusplus
}
#endif

#if (defined(RTI_WIN32) || defined (RTI_WINCE) || defined(RTI_INTIME)) && defined(NDDS_USER_DLL_EXPORT)
/* If the code is building on Windows, stop exporting symbols.
*/
#undef NDDSUSERDllExport
#define NDDSUSERDllExport
#endif

#endif /* SimpleTypePlugin_489918098_h */

