# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Looked at https://github.com/ArgosyLabs/wgnlpy/

from base64 import b64encode, b64decode
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey, X25519PrivateKey


class Key:
    __slots__ = ('__value')

    def __init__(self, key=bytes(32)):
        if isinstance(key, Key):
            self.__value = key.__value
        elif isinstance(key, bytes):
            self.__value = key
        elif isinstance(key, bytearray):
            self.__value = bytes(key)
        elif isinstance(key, str):
            self.__value = b64decode(key)
        else:
            raise TypeError()

        assert isinstance(self.__value, bytes)
        assert 32 == len(self.__value)

    def __str__(self):
        return b64encode(self.__value).decode('utf-8')

    def __bytes__(self):
        return self.__value

    def __repr__(self):
        return f'{type(self).__name__}({repr(str(self))})'

    def __bool__(self):
        return self.__value != bytes(32)

    def __eq__(self, other):
        if isinstance(other, Key):
            return self.__value == other.__value
        elif isinstance(other, (bytes, bytearray)):
            return self.__value == other
        elif isinstance(other, str):
            return self.__value == b64decode(other)
        else:
            return NotImplemented

    def __hash__(self):
        return hash(self.__value)


class PublicKey(Key):
    def __init__(self, key=None):
        if key is None:
            super().__init__()
        elif isinstance(key, PublicKey):
            super().__init__(key)
        elif isinstance(key, X25519PublicKey):
            super().__init__(key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ))
        elif isinstance(key, (bytes, bytearray)):
            super().__init__(X25519PublicKey.from_public_bytes(key).public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ))
        elif isinstance(key, str):
            super().__init__(X25519PublicKey.from_public_bytes(b64decode(key)).public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ))
        else:
            raise TypeError("key must be PublicKey, bytes, bytearray, or str")

    def __eq__(self, other):
        if isinstance(other, Key) and not isinstance(other, PublicKey):
            return NotImplemented

        return super().__eq__(other)

    def __hash__(self):
        return super().__hash__()


class PrivateKey(Key):
    def __init__(self, key=None):
        if key is None:
            super().__init__()
        elif isinstance(key, PrivateKey):
            super().__init__(key)
        elif isinstance(key, X25519PrivateKey):
            super().__init__(key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        elif isinstance(key, (bytes, bytearray)):
            super().__init__(X25519PrivateKey.from_private_bytes(key).private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        elif isinstance(key, str):
            super().__init__(X25519PrivateKey.from_private_bytes(b64decode(key)).private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        else:
            raise TypeError("key must be PrivateKey, bytes, bytearray, or str")

    def __eq__(self, other):
        if isinstance(other, Key) and not isinstance(other, PrivateKey):
            return NotImplemented

        return super().__eq__(other)

    def __hash__(self):
        return super().__hash__()

    def public_key(self):
        return PublicKey(X25519PrivateKey.from_private_bytes(bytes(self)).public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ))

        if isinstance(other, Key) and not isinstance(other, PrivateKey):
            return NotImplemented

        return super().__eq__(other)

    @staticmethod
    def generate():
        return PrivateKey(X25519PrivateKey.generate().private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ))

#