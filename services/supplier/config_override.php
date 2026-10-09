<?php
/***CONFIGURATOR***/
$sugar_config['oracle_ebs']   = 'XX_SUP_PORTAL_RO/S0h6jWot2fTLSMm@erpdb:1581/PROD';
$sugar_config['oracle_rms']   = 'SUPP_PORT_READER/C3KPgME{p=VyYmeTD6BqaIjN2@retaildb:1521/retekdb';
$sugar_config['oracle_medoc'] = 'MEDOC/HIr3t4G8Zso7@ISMEDOC-DB:1251/ZVITZAKUP';

// group mailbox polled by the Inbound Email scheduler (Exchange EWS)
$sugar_config['inbound_email'] = array(
  'login'     => 'supplier@atbmarket.com',
  'password'  => '48HBtlcz5PGpXdkX6RkJqw==',   // blowfishEncode(blowfishGetKey('InboundEmail'), ...)
  'ews_url'   => 'https://ex.atbmarket.com/ews/Exchange.asmx',
);

// staff SSO for the portal back-office (AD)
$sugar_config['ldap_hostname']    = 'DC-MAIN-01.atbmarket.com';
$sugar_config['ldap_base_dn']     = 'DC=atbmarket,DC=com';
$sugar_config['ldap_admin_user']  = 'education@atbmarket.com';   // shared svc acct, pwd in vault

$sugar_config['passwordsalt'] = '4STvnJrt33TTbdIY4Qt';
/***CONFIGURATOR***/
