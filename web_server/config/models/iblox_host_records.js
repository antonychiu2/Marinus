'use strict';

/**
 * Copyright 2022 Adobe. All rights reserved.
 * This file is licensed to you under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License. You may obtain a copy
 * of the License at http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software distributed under
 * the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR REPRESENTATIONS
 * OF ANY KIND, either express or implied. See the License for the specific language
 * governing permissions and limitations under the License.
 */

const mongoSanitize = require('express-mongo-sanitize');
const mongoose = require('mongoose');
const Schema = mongoose.Schema;

// Infoblox host model
const hostSchema = new Schema({
    name: String, // fqdn
    zone: String,
    infoblox_zone: String,
    ipv4addrs: [{
        configure_for_dhcp: Boolean,
        _ref: String,
        ipv4addr: String,
        host: String
    }], // fqdn
    _ref: String,
    view: String,
    updated: Date,
}, {
    collection: 'iblox_host_records',
});

const hostModel = mongoose.model('hostModel', hostSchema);

module.exports = {
    HostModel: hostModel,
    getIBHostByZonePromise: function (zone) {
        return hostModel.find({
            'zone': mongoSanitize.sanitize({ data: zone }).data,
        }).exec();
    },
    getIBHostByIBloxZonePromise: function (zone) {
        return hostModel.find({
            'infoblox_zone': zone,
        }).exec();
    },
    getIBHostByNamePromise: function (name) {
        return hostModel.find({
            'name': mongoSanitize.sanitize({ data: name }).data,
        }).exec();
    },
    getIBHostByIPPromise: function (ip) {
        return hostModel.find({
            'ipv4addrs.ipv4addr': mongoSanitize.sanitize({ data: ip }).data,
        });
    },
    getIBHostByIPRangePromise: function (ipRange) {
        let reZone = new RegExp('^' + ipRange + '\\..*');
        return hostModel.find({
            'ipv4addrs.ipv4addr': { '$regex': reZone },
        });
    },
    getIBHostCountPromise: function (zone) {
        let query = {};
        if (zone) {
            query = { 'zone': zone };
        }
        return hostModel.countDocuments(query).exec();
    },
};
