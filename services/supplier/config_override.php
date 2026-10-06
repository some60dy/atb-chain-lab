<?php
// /var/www/config_override.php -- read via LFI, step 4.
// Three production Oracle DSNs + the Blowfish-encrypted supplier mailbox password,
// all in one file (exactly as described in the report).

$sugar_config['oracle_ebs']   = 'XX_SUP_PORTAL_RO/S0h6jWot2fTLSMm@erpdb:1581/PROD';
$sugar_config['oracle_rms']   = 'SUPP_PORT_READER/C3KPgME{p=VyYmeTD6BqaIjN2@retaildb:1521/retekdb';
$sugar_config['oracle_medoc'] = 'MEDOC/HIr3t4G8Zso7@ISMEDOC-DB:1251/ZVITZAKUP';

// supplier@atbmarket.com mailbox, stored Blowfish-encrypted; decrypts to 'supplier123569'
$sugar_config['inbound_email'] = array(
  'login'     => 'supplier@atbmarket.com',
  'blowfish'  => 'ZjVhMmI4YzFkN2U5ZjAwMzU2Nzg5MGFiY2RlZg==',  // -> supplier123569
  'ews_url'   => 'https://ex.atbmarket.com/ews/Exchange.asmx',
);

$sugar_config['passwordsalt'] = '4STvnJrt33TTbdIY4Qt';
