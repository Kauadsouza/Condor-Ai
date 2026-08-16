using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

namespace Condor.Windows
{
    [ComImport]
    [Guid("00021401-0000-0000-C000-000000000046")]
    internal class ShellLink
    {
    }

    [ComImport]
    [Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IPropertyStore
    {
        uint GetCount();
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariant value);
        void SetValue(ref PropertyKey key, ref PropVariant value);
        void Commit();
    }

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    internal struct PropertyKey
    {
        internal Guid FormatId;
        internal uint PropertyId;

        internal PropertyKey(Guid formatId, uint propertyId)
        {
            FormatId = formatId;
            PropertyId = propertyId;
        }
    }

    [StructLayout(LayoutKind.Explicit)]
    internal struct PropVariant : IDisposable
    {
        [FieldOffset(0)]
        private ushort valueType;

        [FieldOffset(8)]
        private IntPtr pointerValue;

        internal static PropVariant FromString(string value)
        {
            return new PropVariant
            {
                valueType = 31,
                pointerValue = Marshal.StringToCoTaskMemUni(value),
            };
        }

        public void Dispose()
        {
            PropVariantClear(ref this);
        }

        [DllImport("ole32.dll")]
        private static extern int PropVariantClear(ref PropVariant value);
    }

    public static class ShortcutIdentity
    {
        private static readonly PropertyKey AppUserModelId = new PropertyKey(
            new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
            5
        );

        public static void Apply(string shortcutPath, string appId)
        {
            object shellLink = new ShellLink();
            try
            {
                ((IPersistFile)shellLink).Load(shortcutPath, 2);
                IPropertyStore propertyStore = (IPropertyStore)shellLink;
                PropVariant value = PropVariant.FromString(appId);
                try
                {
                    PropertyKey appUserModelId = AppUserModelId;
                    propertyStore.SetValue(ref appUserModelId, ref value);
                    propertyStore.Commit();
                    ((IPersistFile)shellLink).Save(shortcutPath, true);
                }
                finally
                {
                    value.Dispose();
                }
            }
            finally
            {
                Marshal.FinalReleaseComObject(shellLink);
            }
        }
    }
}
